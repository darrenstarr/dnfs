# dnfs — Distributed NFS multipath client project

## Overview

Goal: **single NFS mount command** delivering 40+ Gb/s single-stream and 160+ Gb/s aggregate throughput against a Huawei OceanStor Pacific 9550 storage array. The server has 2x100GbE NICs (non-bonded, `enp65s0f0np0` + `enp65s0f1np1`). The storage presents 8 virtual ports (`fc07:2::11`–`fc07:2::18`) across 16x25GbE links in LACP bundles on CE6866 switches.

Current state: achieved 180.3 Gb/s aggregate and 39.5 Gb/s single-stream using 8 separate NFSv4.1 mounts (one per storage IP) with stock kernel and `nconnect=16`. Working toward a single-mount solution using a custom kernel module — blocked by OceanStor assigning different NFSv4.1 clientids per virtual port (session trunking fails). Documented what we need from Huawei to fix this (`docs/huawei-requirements.md`).

Tag: `pre-nfsv4.0` marks the point before the NFSv4.0 experiment. All active branch: `stage1/nfs41-multipath` (also `main` locally, but `main` is protected on GitHub and requires PR #13).

---

## Repo structure

```
dnfs/
├── AGENTS.md                              # This file
├── README.md                              # Project goals, architecture, build instructions
├── .gitignore                             # Ignores private/ and *.orig
│
├── docs/
│   ├── nfs-ebook/                         # NFS protocol deep-dive eBook
│   ├── sunrpc-book/                       # SunRPC on Linux — kernel developer's guide
│   └── stage2-io-striping.md              # Stage 2 I/O striping architecture
│
├── patches/
│   ├── series                             # 7-patch series ordering
│   └── updates/                           # 8 patch files (0000 cover letter + 0001–0006)
│
├── linux-source-7.0.0/                    # Partial Ubuntu 7.0.0 kernel tree
│   ├── fs/nfs/                            # ~90 NFS client source files (.c + .orig backups)
│   │   ├── nfs_multipath.c                # Our kernel-tree multipath parser (190 lines)
│   │   ├── nfs4client.c                   # Where patch 0006 adds transport creation
│   │   ├── nfs4proc.c                     # Where the diskpool03 hook is patched
│   │   └── internal.h                     # Patched to add dnfs fields
│   ├── include/linux/                     # NFS/SunRPC headers
│   │   └── nfs_fs_sb.h                    # struct nfs_server (we added multipath_clients)
│   └── net/sunrpc/                        # SunRPC layer
│
├── fs/nfs/                                # Standalone multipath implementation (different API)
│   ├── nfs_multipath.c                    # Global singleton parser (92 lines)
│   └── nfs_multipath.h                    # Standalone header
│
├── tests/
│   ├── Makefile                           # User-space unit tests with mocks
│   ├── unit/test_nfs_multipath.c          # 600-line, 23 test cases
│   ├── mocks/                             # Kernel header mocks for userspace compilation
│   └── integration/                       # 18 scripts for kernel build & diskpool03 testing
│
├── ansible/                               # Ansible automation for diskpool03
│   ├── ansible.cfg
│   ├── inventory/production/{hosts,group_vars/all.yml}
│   ├── playbooks/deploy.yml
│   └── roles/{network,kernel,nfs_mount,benchmark}/
│
└── private/                               # gitignored — sensitive/detailed docs
    ├── enfs-documentation.md              # Old enfs-dkms 0.1.6 reference
    └── huawei-requirements.md             # What we need from Huawei
```

---

## Target Machine: diskpool03

- **Hostname**: `diskpool03.gridstorage.uiocloud.no`
- **OS**: Ubuntu 26.04, kernel 7.0.0-15-generic
- **CPU**: 128 cores (Supermicro AS-1115CS-TNR)
- **RAM**: 188 GB
- **SSH chain**: `local → jumpy (158.36.191.160:2222, user darren) → diskpoolmgmt (109.105.125.102) → diskpool03 (user netadmin)`
- **SSH config** (in `~/.ssh/config`):
  ```
  Host jumpy
      Hostname 158.36.191.160
      User darren
      Port 2222
  Host diskpoolmgmt
      Hostname 109.105.125.102
      User darren
      ProxyJump jumpy
  Host diskpool03
      Hostname diskpool03.gridstorage.uiocloud.no
      ProxyJump diskpoolmgmt
      User netadmin
  ```

### Network topology

```
                    SERVER (diskpool03)
         enp65s0f0np0 (100GbE)    enp65s0f1np1 (100GbE)
         MAC: 3c:ec:ef:5c:7d:a8   MAC: 3c:ec:ef:5c:7d:a9
              │                          │
         storagea.1001 (VLAN 1001)  storageb.1001 (VLAN 1001)
     IP: fc07:2::1:a:24/64     IP: fc07:2::2:a:24/64
         MTU: 9134                  MTU: 9134
              │                          │
         ┌────┴────┐              ┌────┴────┐
         │ CE6866  │   LACP       │ CE6866  │   LACP
         │ Switch 1│  8×25GbE     │ Switch 2│  8×25GbE
         └────┬────┘              └────┬────┘
              │                          │
    ┌─────────┴──────────────────────────┴─────────┐
    │         Huawei OceanStor Pacific 9550         │
    │  8 virtual ports: fc07:2::11 through ::18     │
    │  Each on /dCache export                       │
    └───────────────────────────────────────────────┘
```

### Storage IPs and routing

The storage has 8 IPs (`fc07:2::11`–`fc07:2::18`), each with a different MAC address — these are separate virtual port channels on different storage controllers.

**Host routes** required to pin traffic to specific NICs:
```
fc07:2::11/128 → storagea.1001  (default subnet route covers this)
fc07:2::12/128 → storageb.1001
fc07:2::13/128 → storagea.1001
fc07:2::14/128 → storageb.1001
fc07:2::15/128 → storagea.1001
fc07:2::16/128 → storageb.1001
fc07:2::17/128 → storagea.1001
fc07:2::18/128 → storageb.1001
```

Without these host routes, ALL traffic uses `storagea.1001` (lower metric). With them, 4 IPs go through each NIC, giving the CE6866 LACP hash 8× more entropy.

### Kernel module build environment

- **Source**: `~/kernel-build/linux-source-7.0.0/` (partial tree with NFS + SunRPC)
- **Build command**: `make -C /lib/modules/7.0.0-15-generic/build M=$HOME/kernel-build/linux-source-7.0.0/fs/nfs modules`
- **Install**: Copy `nfs.ko` and `nfsv4.ko` to `/lib/modules/7.0.0-15-generic/updates/`
- **Reload**: `modprobe -r nfsv4 nfs && modprobe nfs` (often fails — modules in use by nfsd)
  - Workaround: `sudo umount /proc/fs/nfsd && rmmod nfsd nfsv4 nfs && modprobe nfs`
  - Or just reboot (cleanest)

### Test files

The 20GB test file is at `/dcache/pool1/test20g` (or `/dcache/poolA/test20g` depending on mount point naming). All 8 mounts share `/dCache` export so the file is visible via all mount points.

**WARNING**: The local root disk (`/dev/mapper/ubuntu--vg-ubuntu--lv`, 98GB) fills up easily. When NFS mounts are absent, file writes fall through to the local disk. Clean with `rm -rf /dcache/pool*/cold* /dcache/pool*/bigfile` etc.

---

## Performance Results

All results with stock kernel 7.0.0-15-generic, `rsize=wsize=1M`, `nconnect=16`, MTU 9134, NFSv4.1.

### Single mount, single process

| Test | Throughput | Gb/s |
|------|-----------|------|
| Read (1 job, iodepth=64, direct) | 4.60 GiB/s | **39.5 Gb/s** |
| Read (1 job, iodepth=32, direct) | 4.26 GiB/s | 36.6 Gb/s |
| Write (buffered, 1 job) | 2.49 GiB/s | 21.4 Gb/s |

### 8 mounts (separate nfs_clients)

| Test | Throughput | Gb/s |
|------|-----------|------|
| Aggregate read (single file, 8 offsets) | 21.1 GiB/s | **180.3 Gb/s** |
| Aggregate write (8 different files) | 16.8 GiB/s | **144.3 Gb/s** |
| Aggregate write (SAME file, 8 offsets) | 4.2 GiB/s | 36.1 Gb/s |

Single-file writes collapse due to NFS inode lock contention on the server. Different files scale cleanly. Reads are lock-free either way.

### NFSv4.0 vs v4.1

| Version | Single-stream read | Aggregate |
|---------|-------------------|-----------|
| NFSv4.0 | 3.69 GiB/s (31.7 Gb/s) | Mounts hang |
| NFSv4.1 | 4.60 GiB/s (39.5 Gb/s) | 21.1 GiB/s (180.3 Gb/s) |

NFSv4.1 wins. V4.0 mounts to multiple IPs hang (SETCLIENTID overhead). V4.1's session slot table (64 slots per session) gives higher concurrency than v4.0's RPC congestion window.

### Benchmark commands

```bash
# Single-stream read
echo 3 > /proc/sys/vm/drop_caches
fio --name=read --filename=/dcache/pool1/test20g --rw=read \
    --bs=1M --size=10G --numjobs=1 --iodepth=64 --ioengine=libaio \
    --direct=1 --runtime=10 --time_based --group_reporting

# Aggregate read (8 mounts, single file, different offsets)
echo 3 > /proc/sys/vm/drop_caches
fio --name=m1 --filename=/dcache/pool1/test20g --rw=read --bs=1M \
    --offset=0 --size=2560M --numjobs=1 --iodepth=16 --ioengine=libaio \
    --direct=1 --runtime=10 --time_based \
    ... (m2 through m8, offsets step by 2560M, mount points pool2..pool8) \
    --group_reporting
```

---

## The Session Trunking Problem (BLOCKER for single-mount)

### What we're trying to achieve

A **single** mount command:
```
mount -t nfs4 -o vers=4.1,remoteaddrs=fc07:2::11~fc07:2::12~...~fc07:2::18 \
    fc07:2::11:/dCache /mnt
```

### Our kernel module (patches/updates/)

Our 6-patch series adds `remoteaddrs=` and `localaddrs=` mount options to the NFSv4.1 client:

1. **Patch 1** (`Kconfig` + `Makefile`): Adds `CONFIG_NFS_MULTIPATH` config option, compiles `nfs_multipath.o`
2. **Patch 2** (`internal.h`): Adds `struct nfs_multipath_addrs` (count+flexible-array sockaddr_storage) and `dnfs_remoteaddrs` fields to `nfs_fs_context`, `nfs_client_initdata`, `nfs_server`
3. **Patch 3** (`fs_context.c` + `nfs_multipath.c`): Parses `remoteaddrs=10.0.0.1~10.0.0.2~10.0.0.3` via `rpc_pton()`, bounded to 4096 bytes / 32 addrs
4. **Patch 4** (`client.c`): Propagates address list through `nfs_get_client()` → `cl_dnfs_info`
5. **Patch 5** (`super.c`): Transfers ownership during mount, frees on unmount
6. **Patch 6** (`nfs4client.c`): After session establishment, `rpc_clnt_add_xprt()` per extra address → stock SunRPC round-robin

### The diskpool03 custom module

The running custom module on diskpool03 uses a **different approach** than the patch series:
- A **global singleton** pattern (`static struct nfs_multipath_addrs *g_addrs`)
- Parser stores addresses in the global during mount option parsing
- Hook in `nfs4proc.c` (inserted by `patch_diskpool03.py`) calls `nfs_multipath_get_addrs()` after session creation
- Creates transports via `rpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL)` with `NULL` setup (bypassing trunking test)

### Build recipe for the custom module

The source lives at `~/kernel-build/linux-source-7.0.0/fs/nfs/`. Key files:
- `nfs_multipath.c` — global singleton parser (parse remoteaddrs plus localaddrs)
- `nfs_multipath.h` — struct definition + function declarations
- `fs_context.c` — patched to add `Opt_remoteaddrs`/`Opt_localaddrs` + case handlers
- `nfs4proc.c` — patched with inline declarations and the multipath hook
- `Makefile` — includes `nfs_multipath.o`
- `Kconfig` — adds `config NFS_MULTIPATH` option

**Build command that works**:
```bash
cd ~/kernel-build/linux-source-7.0.0
# Copy Module.symvers from running kernel
sudo cp /lib/modules/7.0.0-15-generic/build/Module.symvers .
# Build against running kernel headers
sudo make -C /lib/modules/7.0.0-15-generic/build M=$PWD/fs/nfs modules
# Install manually (modules_install installs wrong file)
sudo cp fs/nfs/nfs.ko /lib/modules/7.0.0-15-generic/updates/
sudo cp fs/nfs/nfsv4.ko /lib/modules/7.0.0-15-generic/updates/
sudo depmod -a
sudo reboot  # safest way to load new modules
```

**Common build issues**:
- `make M=fs/nfs` from the partial tree fails (wrong Module.symvers)
- `make -C /lib/modules/.../build M=$PWD/fs/nfs` is the correct command
- `#include "nfs_multipath.h"` not found — the kernel include paths don't include `fs/nfs/`
  - Fix: include `<linux/nfs_multipath.h>` with symlink, OR put declarations inline in nfs4proc.c
- `make modules_install` installs the STOCK module, not ours
  - Fix: manually `cp` the .ko files as shown above
- `modprobe -r nfsv4 nfs` fails because modules are in use
  - Fix: reboot after install

### Why it fails (root cause)

The transport creation WORKS — transports appear in `ss -tnp6` output. But they carry **zero data**. The sequence:

1. Hook calls `rpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL)` — transport added to xprt_switch
2. SunRPC round-robin dispatches an NFS operation to the new transport
3. The COMPOUND carries a `SEQUENCE` op with the session ID from the PRIMARY mount
4. The OceanStor virtual port at the new IP has a **different `clientid`** — the session is bound to the primary's clientid
5. Server returns `NFS4ERR_BAD_SESSION`
6. Transport goes offline, state manager probes it with `nfs4_test_session_trunk` (`fs/nfs/nfs4proc.c:8890`)
7. `nfs4_detect_session_trunking` (`fs/nfs/nfs4client.c:544`) checks:
   - `clp->cl_clientid != res->clientid` ← **FAILS** (different virtual port = different clientid)
   - `server_owner.major_id` must match
   - `server_owner.minor_id` must match
   - `server_scope` must match
8. On failure: `rpc_clnt_xprt_switch_remove_xprt()` removes the transport

### The fix we need from Huawei

One change: **return the same `clientid` in `EXCHANGE_ID` responses across all virtual ports** for a given client `co_ownerid`. The `server_owner` and `server_scope` should already match (same storage system). No architectural change, no network reconfiguration, no shared state needed.

Full requirements documented in `docs/huawei-requirements.md`.

### NFSv4.0 experiment (dead end)

We tested NFSv4.0 (no sessions, no trunking) hoping to bypass the problem. Results:
- V4.0 has higher RPC congestion window (32 per transport) vs v4.1 session slots (64)
- But single-stream dropped to 31.7 Gb/s (vs 39.5 Gb/s)
- Multi-mount to different IPs hangs with v4.0
- Conclusion: v4.1 is better, v4.0 doesn't solve the multipath problem

---

## Stage 2: I/O Striping Architecture

Documented in `docs/stage2-io-striping.md`. Core idea:

1. **Intercept at `nfs_pageio_do_io()`** in `pagelist.c` — after pages accumulated, before RPC submission
2. **Split into stripes** — one `rsize`/`wsize` chunk per stripe, bound to a specific transport via `rpc_task_set_xprt()`
3. **Concurrent dispatch** — all stripes issued in parallel on different transports
4. **Completion aggregation** — `atomic_dec_and_test(&remaining)` collector

A 4MB read on 9 transports with `rsize=1MB` becomes nine 1MB reads dispatched in parallel, aggregated on completion. No server protocol changes.

Only needed for single-stream performance. Multi-stream already distributes via SunRPC round-robin.

---

## Java NIO transferTo() Investigation

Cloned OpenJDK (https://github.com/openjdk/jdk, /tmp/jdk21) to find where 8KB/16KB reads happen.

### The problem

`FileChannel.transferTo()` has three paths:

**Path 1** (`transferToDirect`, `FileChannelImpl.java:810`):
- JNI → Linux `sendfile()` / `copy_file_range()`
- Kernel-space copy, no userspace buffers
- Returns `UNSUPPORTED` on failure → caches `transferToDirectNotSupported = true`
- Once unsupported, ALL subsequent calls skip this path

**Path 2** (`transferToTrustedChannel`, `FileChannelImpl.java:853`):
- Uses mmap (8MB chunks) for transfers ≥16KB to FileChannel/SocketChannel
- Threshold: `MAPPED_TRANSFER_THRESHOLD = 16*1024`

**Path 3** (`transferToArbitraryChannel`, `FileChannelImpl.java:905`) ← **THE 8KB PROBLEM**:
```java
private static final int TRANSFER_SIZE = 8192;  // Line 1082

private long transferToArbitraryChannel(long position, long count, ...) {
    int c = (int) Math.min(count, TRANSFER_SIZE);
    ByteBuffer bb = ByteBuffer.allocate(c);
    while (tw < count) {
        bb.limit((int) Math.min(count - tw, TRANSFER_SIZE));
        int nr = read(bb, position + tw);   // 8KB read from NFS
        bb.flip();
        tw += target.write(bb);
        bb.clear();
    }
    return tw;
}
```

This is a userspace read/write loop — each 8KB read becomes an NFS READ RPC. Catastrophic for throughput.

### Fix plan

Three options:

1. **Reflection hack** — Remove `final` on `TRANSFER_SIZE` via `Field.modifiers`, set to 1MB. Fragile across JDK versions.

2. **Java Agent** — `java.lang.instrument` + ASM/Javassist to patch at class load time.

3. **Custom JDK build** (cleanest) — Change `TRANSFER_SIZE = 8192` to `1048576` in `FileChannelImpl.java:1082`, rebuild OpenJDK.

### Other important constants

- `maxDirectTransferSize()` returns `0x7ffff000` (~2GB) on Linux (`FileDispatcherImpl.java:35`)
- `MAPPED_TRANSFER_THRESHOLD = 16*1024` — below this, mmap path is skipped
- `MAPPED_TRANSFER_SIZE = 8*1024*1024` — mmap chunk size

### Key source file locations

- `/tmp/jdk21/src/java.base/share/classes/sun/nio/ch/FileChannelImpl.java` — lines 810-984 (transferTo paths)
- `/tmp/jdk21/src/java.base/linux/classes/sun/nio/ch/FileDispatcherImpl.java` — maxDirectTransferSize, native dispatch
- `/tmp/jdk21/src/java.base/linux/native/libnio/ch/FileDispatcherImpl.c` — sendfile() JNI (lines 81-127)

---

## Custom Kernel Module — Current State on Diskpool03

### What works
- Mount with `remoteaddrs=` and `localaddrs=` options (parsed correctly)
- Transport creation to additional IPs (verified via `ss -tnp6` and dmesg)
- `nconnect=16` (NFS_MAX_CONNECTIONS bumped to 32 in source)
- 9 data TCP connections per nfs_client (the practical max)
- Single-stream read at 39.5 Gb/s (stock module) or 42.1 Gb/s (custom module)
- No crashes after fixing the `servername` and `addrlen` in the xprt_create struct

### What doesn't work
- Operations on extra transports fail (session trunking — OceanStor clientid mismatch)
- Module reload often fails (`modprobe -r` blocked by in-use modules)
- Build pipeline is fragile (Module.symvers, include paths, manual .ko copying)
- `make modules_install` installs the wrong module

### Source file locations on diskpool03
- Build root: `/home/netadmin/kernel-build/linux-source-7.0.0/`
- NFS source: `/home/netadmin/kernel-build/linux-source-7.0.0/fs/nfs/`
- Patcher script: `/home/netadmin/kernel-build/linux-source-7.0.0/fs/nfs/patch_diskpool03.py`
- Stock source for recovery: `/lib/modules/7.0.0-15-generic/kernel/fs/nfs/nfs.ko.zst` (and nfsv4.ko.zst)
- Installed modules: `/lib/modules/7.0.0-15-generic/updates/`

---

## Ansible Automation

Located in `ansible/`. 4 roles with Python library modules:

| Role | Module | Purpose |
|------|--------|---------|
| `network` | `ipv6_route.py` | /128 host routes across both 100GbE NICs |
| `kernel` | `nfs_module_build.py` | Patch NFS_MAX_CONNECTIONS, rebuild, install, reload |
| `nfs_mount` | `nfs_multipath_mount.py` | 8 NFSv4.1 mounts, one per storage IP |
| `benchmark` | `nfs_benchmark.py` | fio single/aggregate read/write with thresholds |

Variables in `inventory/production/group_vars/all.yml`. Tags: `network`, `kernel`, `nfs`, `benchmark`, `verify`, `always`.

Run with: `ansible-playbook playbooks/deploy.yml`

---

## Git State

- **Active branch**: `stage1/nfs41-multipath` (pushed to origin)
- **Local main**: synced with stage1 (fast-forwarded)
- **Remote main**: protected, requires PR (#13)
- **Tag**: `pre-nfsv4.0` — marks state before NFSv4.0 experiment
- **Stale branches deleted**: docs/enfs-annex, docs/nfs-ebook, docs/nfsv3-chapter, docs/readme, docs/sunrpc-book, docs/sunrpc-deviations, feat/agents-update, feat/opencode-mcp

### Recent commits (most recent first)
```
1d83b40 ansible: complete deploy playbook for diskpool03 NFS multipath
7858f08 docs: Stage 2 I/O striping architecture + Huawei requirements document
b71eb8e stage1: verified multipath on diskpool03 against Huawei OceanStor
0d22179 fix: Opt_tcp fall-through bug, add LD_PRELOAD + mount test tools
9011e9a chore: ignore .orig backup files
127c79d clean: remove stale test artifacts, keep only current tests
0646184 rename: dnfs → nfs_multipath (standard kernel naming)
318ec7a stage1: working dnfs implementation with build, install, and mount verified
034b106 stage1: unit tests, integration tests, and patch verification
d71edac stage1: NFSv4.1 client multipath patch series
```

---

## Key Architectural Decisions & Lessons

### 1. Session trunking is NOT bypassable
We tried `rpc_clnt_add_xprt` with `NULL` setup (no trunking check). Transport gets added, but operations fail with `NFS4ERR_BAD_SESSION`. The state manager later probes and removes the transport. The OceanStor's per-virtual-port clientids are the root cause.

### 2. Separate nfs_clients work but require multiple mounts
Our 8-mount approach creates 8 nfs_clients (different server IP = different client), each with 9 data connections (nconnect=16, capped at 9). Total: 72 connections delivering 180 Gb/s.

### 3. nconnect cap at 9 data connections
Even with `NFS_MAX_CONNECTIONS=32`, only 9 data connections per mount are created. The cap is in `rpc_clnt_add_xprt` or the transport creation loop — reason unknown but consistent across module versions.

### 4. Write scaling is inode-locked
Single-file writes from multiple nfs_clients collapse to ~36 Gb/s (NFS inode lock). Different files scale to 144 Gb/s.

### 5. MTU is critical
Default `net.ipv6.conf.all.mtu` was 1280 (minimum IPv6 MTU). Setting it to 9000+ and interface MTU to 9134 (jumbo frames) was essential for performance.

### 6. IPv6 ECMP is limited
The `ip -6 route replace ... nexthop ... nexthop` API requires `via ADDRESS`, not `dev INTERFACE`. For device-only routes, use source-based policy routing with separate tables instead.

### 7. LACP hash entropy matters
The CE6866 default LACP hash includes: {src-mac, dst-mac, src-ip, dst-ip, src-port, dst-port, protocol}. Using 8 different destination IPs (different MACs) provides 8× more hash entropy than 2 IPs.

---

## Next Steps

1. **Huawei fix** — Await response on unified clientid across virtual ports
2. **If Huawei fixes clientid**: The custom kernel module works as-is — no code changes needed
3. **If Huawei can't fix**: Implement multi-nfs_client creation in the kernel module (one nfs_client per remote IP, shared under one mount)
4. **I/O striping**: Implement Stage 2 from `docs/stage2-io-striping.md` once multipath transports are functional
5. **Java NIO fix**: Implement the TRANSFER_SIZE patch (reflection agent or custom JDK build)
6. **Ansible test**: Run the full Ansible playbook against a fresh diskpool03 to verify reproducibility

---

## Useful Commands

### SSH to diskpool03
```bash
ssh diskpool03
```

### Quick performance test
```bash
ssh diskpool03 'sudo sh -c "echo 3 > /proc/sys/vm/drop_caches" && \
  sudo fio --name=read --filename=/dcache/pool1/test20g --rw=read \
  --bs=1M --size=4G --numjobs=1 --iodepth=32 --ioengine=libaio \
  --direct=1 --runtime=5 --time_based --group_reporting 2>&1 | grep bw='
```

### Check connections
```bash
ssh diskpool03 'ss -tnp6 state established | grep -c 2049'
```

### Check mounts
```bash
ssh diskpool03 'mount | grep dCache'
```

### Check NFS stats
```bash
ssh diskpool03 'cat /proc/self/mountstats | grep -A2 "device \[fc07"'
```

### Clean up all NFS mounts
```bash
ssh diskpool03 'sudo umount -a -t nfs4'
```

### View multipath dmesg
```bash
ssh diskpool03 'sudo dmesg | grep -E "mpath|multipath|trunking"'
```

### Restore stock kernel module
```bash
ssh diskpool03 '
sudo umount -a -t nfs4
sudo modprobe -r nfsv4 nfs 2>/dev/null
sudo cp /lib/modules/7.0.0-15-generic/kernel/fs/nfs/nfs.ko.zst /tmp/
sudo unzstd -f /tmp/nfs.ko.zst -o /lib/modules/7.0.0-15-generic/updates/nfs.ko
sudo cp /lib/modules/7.0.0-15-generic/kernel/fs/nfs/nfsv4.ko.zst /tmp/
sudo unzstd -f /tmp/nfsv4.ko.zst -o /lib/modules/7.0.0-15-generic/updates/nfsv4.ko
sudo depmod -a
sudo modprobe nfs
'
```
