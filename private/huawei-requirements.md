# NFS Multipath on Huawei OceanStor — Performance Report & Requirements

## 1. Performance Results

All results with stock Linux kernel 7.0.0-15-generic, `rsize=wsize=1M`,
`nconnect=16`, MTU 9134, NFSv4.1, 8 mount points to 8 OceanStor virtual ports
(separate nfs_clients, one per server IP).

| Workload | Single-stream | Aggregate / Multi-file |
|----------|---------------|------------------------|
| Read (1 mount) | **4.60 GiB/s (39.5 Gb/s)** | 5.47 GiB/s (47.0 Gb/s) |
| Read (8 mounts, 1 file) | — | **21.0 GiB/s (180.3 Gb/s)** |
| Write (1 mount, 1 file) | **2.49 GiB/s (21.4 Gb/s)** | — |
| Write (8 mounts, 8 files) | — | **16.8 GiB/s (144.3 Gb/s)** |

### 1.1 Setup

```
Server:   2x 100GbE NICs (separate, non-bonded)
           enp65s0f0np0 → storagea.1001 → fc07:2::1:a:24
           enp65s0f1np1 → storageb.1001 → fc07:2::2:a:24

Storage:  Huawei OceanStor Pacific 9550
          16x 25GbE links in LACP bundles across 2x CE6866 switches
          8 virtual ports: fc07:2::11 through fc07:2::18
          Each virtual port has a distinct MAC address

Switches: Huawei CE6866, default LACP hash mode (src/dst MAC, IP, port)
```

### 1.2 Mount configuration

```
mount -t nfs4 -o vers=4.1,proto=tcp6,nconnect=16,rsize=1048576,wsize=1048576 \
    [fc07:2::11]:/dCache /dcache/pool1
mount -t nfs4 -o vers=4.1,proto=tcp6,nconnect=16,rsize=1048576,wsize=1048576 \
    [fc07:2::12]:/dCache /dcache/pool2
... (one per IP, 8 total, with host routes to bind IPs to specific NICs)
```

### 1.3 Why nconnect=16 helps

Stock kernel `NFS_MAX_CONNECTIONS=16`. Each mount creates up to 9 data TCP
connections. With 8 mounts: 72 connections total. The CE6866 LACP hash
(src/dst-MAC, IP, port) distributes each connection across the 16×25GbE
storage links independently.

### 1.4 Single-file write bottleneck

8-stream writes to the SAME file from different mounts collapse to ~36 Gb/s
due to NFS inode lock contention on the server. Different files scale
cleanly to 144 Gb/s.

## 2. The Session Trunking Problem

### 2.1 What we're trying to build

A **single** NFS mount command that achieves both good single-stream (~40 Gb/s)
and aggregate (~160 Gb/s) throughput, using 8 server IP addresses:

```
mount -t nfs4 -o vers=4.1,remoteaddrs=fc07:2::11~fc07:2::12~...~fc07:2::18 \
    fc07:2::11:/dCache /mnt
```

### 2.2 Our kernel module implementation

We built a custom Linux kernel module (patches in `patches/updates/`) that:

1. **Parses** `remoteaddrs=fc07:2::11~fc07:2::12~...` during mount option processing
   (`fs/nfs/nfs_multipath.c`, `fs/nfs/fs_context.c`)

2. **Parses** `localaddrs=fc07:2::1:a:24~fc07:2::2:a:24~...` for per-transport
   source address binding

3. After NFSv4.1 session creation, **calls `rpc_clnt_add_xprt()`** for each additional
   remote address to create additional TCP transports on the same `nfs_client`
   (`fs/nfs/nfs4proc.c`, hook inserted after `rpc_clnt_probe_trunked_xprts`)

4. For single-stream performance, reads need to be **striped** across all transports
   (architecture in `docs/stage2-io-striping.md`)

### 2.3 Why it fails

The transports ARE created (visible in `ss -tnp6` output). But they carry **zero
data**. The sequence is:

**Step 1** — Our hook calls `rpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL)`.
With `setup=NULL`, the session trunking test is skipped and the transport is
added to the `xprt_switch` (SunRPC code at `net/sunrpc/clnt.c:3137-3142`):

```c
rpc_xprt_switch_set_roundrobin(xps);
if (setup) {                    // setup is NULL → skipped
    ret = setup(clnt, xps, xprt, data);
    if (ret != 0)
        goto out_put_xprt;
}
rpc_xprt_switch_add_xprt(xps, xprt);  // transport IS added
```

**Step 2** — An NFS operation (e.g. READ) gets dispatched to the new transport
via SunRPC round-robin.

**Step 3** — The COMPOUND op carries a `SEQUENCE` operation containing the
session ID from the primary mount. The server at the new IP receives it.

**Step 4** — The OceanStor virtual port at the new IP has a **different
`clientid`** than the primary. The session is bound to the primary's clientid.
The server rejects the operation with `NFS4ERR_BAD_SESSION`.

**Step 5** — The transport is marked offline. Later, the NFS state manager
calls `rpc_clnt_probe_trunked_xprts`, which sends EXCHANGE_ID on the transport
and runs the trunking check at (`fs/nfs/nfs4client.c:544-575`):

```c
int nfs4_detect_session_trunking(struct nfs_client *clp,
        struct nfs41_exchange_id_res *res, struct rpc_xprt *xprt)
{
    /* Check eir_clientid — FAILS because different virtual port */
    if (clp->cl_clientid != res->clientid)
        goto out_err;

    /* Check eir_server_owner so_major_id */
    if (!nfs4_check_serverowner_major_id(clp->cl_serverowner,
                                         res->server_owner))
        goto out_err;

    /* Check eir_server_owner so_minor_id */
    if (clp->cl_serverowner->minor_id != res->server_owner->minor_id)
        goto out_err;

    /* Check eir_server_scope */
    if (!nfs4_check_server_scope(clp->cl_serverscope, res->server_scope))
        goto out_err;

    return 0;   // success — transport shares session
out_err:
    return -EINVAL;  // transport removed from switch
}
```

**Step 6** — The trunking test calls `nfs4_test_session_trunk`
(`fs/nfs/nfs4proc.c:8890-8928`). On failure, the transport is **removed**
from the xprt_switch and the TCP connection is torn down:

```c
if (status == 0)
    rpc_clnt_xprt_switch_add_xprt(clnt, xprt);          // on success
else if (...)
    rpc_clnt_xprt_switch_remove_xprt(clnt, xprt);       // on failure!
```

### 2.4 Root cause

Each OceanStor virtual port (`fc07:2::11` through `fc07:2::18`) is a
**separate NFS endpoint** with its own:

- `clientid` (assigned by EXCHANGE_ID)
- `server_owner` (major_id, minor_id)
- Session state
- File handle namespace
- Delegation/lock state

From the Linux NFS client's perspective, each virtual port looks like a
**different NFS server** that happens to export the same filesystem. The
client cannot share a single NFSv4.1 session across different server endpoints.

This is confirmed by inspecting dmesg during mounts:

```
NFS:  fc07:2::11: Session trunking succeeded for fc07:2::11
NFS:  fc07:2::11: Session trunking failed for fc07:2::12
NFS:  fc07:2::11: Session trunking failed for fc07:2::13
...
```

### 2.5 Why NFSv4.0 doesn't help

We tested NFSv4.0 (which has no sessions, no `EXCHANGE_ID`, no trunking test).
Result: single-stream throughput drops from 39.5 Gb/s (v4.1) to 31.7 Gb/s
(v4.0). The session slot table in v4.1 (64 slots, parallel execution) provides
higher concurrency than v4.0's per-transport RPC congestion window.

More importantly, NFSv4.0 doesn't solve the underlying problem: operations
sent to a different virtual port still fail because the filehandles and
stateids from the primary mount aren't valid on the other endpoint.

## 3. What We Need from Huawei

### 3.1 Minimum change: Unified clientid across virtual ports

**The OceanStor should return the same `clientid` in `EXCHANGE_ID` responses
for all virtual ports (`fc07:2::11` through `fc07:2::18`) when the same
NFS client `co_ownerid` is presented.**

If all virtual ports assign the same `clientid` to a given client, session
trunking will succeed:

```
EXCHANGE_ID from client X on fc07:2::11 → clientid = 0x1234...
EXCHANGE_ID from client X on fc07:2::12 → clientid = 0x1234...  (same!)
EXCHANGE_ID from client X on fc07:2::13 → clientid = 0x1234...  (same!)
```

Currently each port returns a different clientid, which is what causes the
trunking test to fail.

### 3.2 Recommended: Unified server_owner and server_scope

For completeness and to ensure the trunking test passes all four checks:

```
nfs4_detect_session_trunking() checks:
  1. clientid        — MUST MATCH (Section 3.1)
  2. server_owner major_id — MUST MATCH (should already match if all ports
                               are the same storage system)
  3. server_owner minor_id — MUST MATCH (ditto)
  4. server_scope     — MUST MATCH (ditto)
```

If all four match, the transport is accepted and can carry operations using
the same session.

### 3.3 What this does NOT require

- **Does NOT require** the virtual ports to share NFS state (open files,
  locks, delegations stay per-controller)

- **Does NOT require** changing the LACP / VLAN / physical network topology

- **Does NOT require** any change to the exported filesystem or mount paths

- **Does NOT require** the controllers to share a common IP or MAC address

### 3.4 Alternative: Unify filehandle namespace

If the storage can present the **same filehandle space** across all virtual
ports (i.e., a filehandle returned by OPEN on port A works on port B), then
the multipath client could distribute operations without session sharing.
This is a larger change but would enable true transport-level multipath.

## 4. What We Do Once Huawei Fixes This

The flow with unified clientids becomes:

```
mount -t nfs4 -o vers=4.1,remoteaddrs=fc07:2::11~...~fc07:2::18,... \
    fc07:2::11:/dCache /mnt
            │
            ▼
    nfs4_proc_create_session()
    ├── EXCHANGE_ID + CREATE_SESSION on ::11 → clientid X, session S
    ├── rpc_clnt_add_xprt to ::12 → EXCHANGE_ID → same clientid X → TRUNKS ✓
    ├── rpc_clnt_add_xprt to ::13 → EXCHANGE_ID → same clientid X → TRUNKS ✓
    ├── ... (6 more)
    │
    ▼
    Single nfs_client with 8×9 = 72 transports in one xprt_switch
    SunRPC round-robin distributes operations across ALL transports
```

**Single-stream**: With 72 transports and I/O striping (splitting large READs
across multiple transports), expected throughput: 40-60 Gb/s from one mount.

**Multi-stream**: 72 transports naturally distribute concurrent operations,
expected throughput: 160-200 Gb/s from one mount.

## 5. Kernel Module Status

Our custom kernel module (`patches/updates/`, files `fs/nfs/nfs_multipath.c`,
`fs/nfs/nfs4proc.c`, `fs/nfs/fs_context.c`) implements the full mount option
parsing and transport creation pipeline. It compiles and loads on kernel
7.0.0-15-generic.

When Huawei resolves the clientid issue, the module will work as-is — the
`rpc_clnt_add_xprt` calls in our hook will succeed because the trunking
test will pass.

The Stage 2 I/O striping design (`docs/stage2-io-striping.md`) provides
the architecture for single-stream performance optimization, which can
be implemented once the basic multipath transport infrastructure is
functional.

## 6. Reference: Test Machine

- **diskpool03**: Ubuntu 26.04, kernel 7.0.0-15-generic, 128 cores
- SSH: `diskpool03` (via jumpy → diskpoolmgmt)
- Storage path: `fc07:2::/64` via VLAN 1001 on enp65s0f0np0 + enp65s0f1np1
- Stock NFS module: `/lib/modules/7.0.0-15-generic/kernel/fs/nfs/nfs.ko.zst`
- Custom module build: `~/kernel-build/linux-source-7.0.0/fs/nfs/`
- Build command: `make -C /lib/modules/7.0.0-15-generic/build M=$PWD/fs/nfs`

## 7. Performance Test Commands (Reproducible)

```bash
# Setup routing (persistent across reboots)
for ip in 12 14 16 18; do
    ip -6 route add fc07:2::${ip}/128 dev storageb.1001
done
for ip in 13 15 17; do
    ip -6 route add fc07:2::${ip}/128 dev storagea.1001
done

# 8 mounts with nconnect=16
for ip in $(seq 11 18); do
    idx=$((ip-10))
    mkdir -p /dcache/pool${idx}
    mount -t nfs4 -o vers=4.1,proto=tcp6,nconnect=16,\
        rsize=1048576,wsize=1048576,noatime,hard \
        [fc07:2::${ip}]:/dCache /dcache/pool${idx}
done

# Single-stream read
echo 3 > /proc/sys/vm/drop_caches
fio --name=read --filename=/dcache/pool1/test20g --rw=read \
    --bs=1M --size=10G --numjobs=1 --iodepth=64 --ioengine=libaio \
    --direct=1 --runtime=8 --time_based --group_reporting

# Aggregate read (single file, 8 mounts, different offsets)
echo 3 > /proc/sys/vm/drop_caches
fio --name=m1 --filename=/dcache/pool1/test20g --rw=read --bs=1M \
    --offset=0 --size=2560M --numjobs=1 --iodepth=16 --ioengine=libaio \
    --direct=1 --runtime=8 --time_based \
    ... (m2 through m8 with different offsets and mount points) \
    --group_reporting
```
