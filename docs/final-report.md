# dCache 2026 Performance Engineering — Final Report

## Performance Evolution

```mermaid
%%{init: {'theme': 'neutral'}}%%
graph LR
    subgraph Baseline
        A["Stock<br/>540 MB/s<br/>4.3 Gb/s"]
    end
    subgraph Stage1
        B["1MB Buffer<br/>1,075 MB/s<br/>8.6 Gb/s<br/>2.0×"]
    end
    subgraph Stage2
        C["Async Pipeline<br/>11,393 MB/s<br/>91.1 Gb/s<br/>21.1×"]
    end
    subgraph Stage3
        D["8-Pool NFSv3<br/>10,145 MB/s<br/>81.2 Gb/s"]
    end
    subgraph Stage4
        E["Dual-NIC<br/>24,700 MB/s<br/>197.6 Gb/s<br/>45.7×"]
    end
    subgraph Final
        F["Cross-Machine<br/>9,760 MB/s<br/>78.1 Gb/s<br/>18.1×"]
    end
    A --> B --> C --> D --> E --> F
    style A fill:#ffcccc
    style F fill:#ccffcc
```

### Throughput Progression

```mermaid
xychart-beta
    title "Throughput Evolution (Gb/s)"
    x-axis ["Stock", "1MB Buffer", "Async Pipeline", "8-Pool", "Dual-NIC", "Cross-Machine"]
    y-axis "Gb/s" 0 --> 200
    bar [4.3, 8.6, 91.1, 81.2, 197.6, 78.1]
```

### Speedup Factor

```mermaid
xychart-beta
    title "Improvement Over Baseline (×)"
    x-axis ["Stock", "1MB Buffer", "Async Pipeline", "8-Pool", "Dual-NIC", "Cross-Machine"]
    y-axis "Speedup" 0 --> 50
    bar [1.0, 2.0, 21.1, 18.8, 45.7, 18.1]
```

### Read vs Write Asymmetry

```mermaid
xychart-beta
    title "Read vs Write Throughput (Gb/s)"
    x-axis ["Read", "Write (local)", "Write (remote)"]
    y-axis "Gb/s" 0 --> 200
    bar [197.6, 86.3, 78.1]
```

| | Read | Write | Ratio |
|---|------|-------|-------|
| **Local** | 197.6 Gb/s | 86.3 Gb/s | 2.3:1 |
| **Remote** | — | 78.1 Gb/s | — |

NFSv3 writes are 2.3× slower than reads. Each write RPC blocks on server acknowledgment.

---

## Network Topology

```mermaid
graph TB
    subgraph Storage["Huawei OceanStor Pacific 9550"]
        C1["Controller 1<br/>fc07:2::11"]
        C2["Controller 2<br/>fc07:2::12"]
        C3["Controller 3<br/>fc07:2::13"]
        C4["Controller 4<br/>fc07:2::14"]
        C5["Controller 5<br/>fc07:2::15"]
        C6["Controller 6<br/>fc07:2::16"]
        C7["Controller 7<br/>fc07:2::17"]
        C8["Controller 8<br/>fc07:2::18"]
    end
    
    subgraph Switches["CE6866 Switches"]
        SWA["CE6866a<br/>Eth-Trunk9-16<br/>8×25GE"]
        SWB["CE6866b<br/>Eth-Trunk9-16<br/>8×25GE"]
    end
    
    subgraph DP01["diskpool01 (128 cores, 372GB)"]
        NIC1A["storagea.1001<br/>fc07:2::1:a:22<br/>enp65s0f0np0"]
        NIC1B["storageb.1001<br/>fc07:2::2:a:22<br/>enp65s0f1np1"]
    end
    
    subgraph DP03["diskpool03 (128 cores, 372GB)"]
        NIC3A["storagea.1001<br/>fc07:2::1:a:24<br/>enp65s0f0np0"]
        NIC3B["storageb.1001<br/>fc07:2::2:a:24<br/>enp65s0f1np1"]
    end
    
    C1 & C3 & C5 & C7 -->|25GE| SWA
    C2 & C4 & C6 & C8 -->|25GE| SWB
    SWA -->|100GE| NIC1A
    SWA -->|100GE| NIC3A
    SWB -->|100GE| NIC1B
    SWB -->|100GE| NIC3B
```

Per-machine NFSv3 mount layout:

```mermaid
graph LR
    M1["/dcache/pool1<br/>→ fc07:2::11"]
    M2["/dcache/pool2<br/>→ fc07:2::12"]
    M3["/dcache/pool3<br/>→ fc07:2::13"]
    M4["/dcache/pool4<br/>→ fc07:2::14"]
    M5["/dcache/pool5<br/>→ fc07:2::15"]
    M6["/dcache/pool6<br/>→ fc07:2::16"]
    M7["/dcache/pool7<br/>→ fc07:2::17"]
    M8["/dcache/pool8<br/>→ fc07:2::18"]
    
    NI["8 × NFSv3<br/>nconnect=16 each<br/>128+ TCP connections"]
    NI --> M1 & M2 & M3 & M4 & M5 & M6 & M7 & M8
```

---

## Kernel Modifications

### Summary

| Layer | Files Changed | Lines Added | Purpose |
|-------|--------------|-------------|---------|
| NFS client | `nfs3client.c`, `pagelist.c`, `fs_context.c`, `nfs4proc.c` | ~175 lines | Transport creation, I/O striping, option parsing |
| New files | `nfs_multipath.c`, `nfs_multipath.h` | ~162 lines | Multipath parser + API |
| Headers | `include/linux/nfs_fs_sb.h` | 1 line | `mpath_num_xprts` field |
| Build | `Kconfig`, `Makefile` | ~15 lines | Config, link, ccflags |
| **Total** | **9 files** | **~355 lines** | No SunRPC changes |

### Change Distribution

```mermaid
pie title "Lines Changed by Component"
    "nfs3client.c" : 100
    "nfs_multipath.c" : 140
    "pagelist.c" : 30
    "nfs4proc.c" : 30
    "fs_context.c" : 15
    "Headers" : 23
    "Build" : 17
```

### Files Detail

#### `fs/nfs/nfs_multipath.c` (NEW, 140 lines)
Global singleton parser for `remoteaddrs=` and `localaddrs=` mount options.
Tilde-separated address lists parsed via `rpc_pton()`. Exports:
- `nfs_multipath_parse()` — parse `remoteaddrs=`
- `nfs_multipath_parse_local()` — parse `localaddrs=`
- `nfs_multipath_get_addrs()` — consume remote list (clear-on-read)
- `nfs_multipath_get_local_addrs()` — consume local list
- `nfs_multipath_free_addrs()` — release memory

#### `fs/nfs/nfs_multipath.h` (NEW, 22 lines)
```c
struct nfs_multipath_addrs {
    unsigned int count;
    unsigned int max;
    struct sockaddr_storage addrs[];
};
#define CONFIG_NFS_MULTIPATH_MAX_ADDRS 32
```

#### `fs/nfs/nfs3client.c` (+100 lines)
`nfs3_multipath_setup()` — called from `nfs3_create_server()` after mount.
Creates full 2×8 mesh: iterates localaddrs × remoteaddrs, calls
`rpc_clnt_add_xprt()` for each pair. No session trunking check needed
(NFSv3 has no sessions). Stores count in `server->mpath_num_xprts`.

```mermaid
sequenceDiagram
    participant Mount
    participant nfs3client
    participant SunRPC
    participant Network
    
    Mount->>nfs3client: nfs3_create_server()
    nfs3client->>SunRPC: nfs3_multipath_setup()
    loop 2 local × 8 remote
        SunRPC->>Network: rpc_clnt_add_xprt()
        Network-->>SunRPC: transport created
    end
    SunRPC-->>nfs3client: 16 transports
    Note over nfs3client: server->mpath_num_xprts = 16
```

#### `fs/nfs/pagelist.c` (+30 lines)
I/O striping via mirror count override. `nfs_pageio_setup_mirroring()`
checks `server->mpath_num_xprts`. If > 1 and request size ≥ threshold,
creates N mirrors — SunRPC round-robins RPC tasks across multipath transports.

#### `fs/nfs/fs_context.c` (+15 lines)
- Enum: `Opt_remoteaddrs`, `Opt_localaddrs`
- `fsparam_string("remoteaddrs", Opt_remoteaddrs)`
- `fsparam_string("localaddrs", Opt_localaddrs)`
- Case handlers calling `nfs_multipath_parse[_local]()`

#### `fs/nfs/nfs4proc.c` (+30 lines)
NFSv4.1 transport creation hook. Inline struct declarations bypass
kernel include path issues (`#include "nfs_multipath.h"` not found in
out-of-tree build). Hook inactive until OceanStor fixes per-port clientid.

#### `include/linux/nfs_fs_sb.h` (+1 line)
```c
unsigned int mpath_num_xprts;  // in struct nfs_server
```

### Build System
- Source: Ubuntu 7.0.0 kernel (`linux-source-7.0.0`)
- Build: `make -C /lib/modules/.../build M=fs/nfs modules`
- Install: `cp nfs.ko nfsv3.ko nfsv4.ko /lib/modules/.../updates/`
- Module srcversion: `DF07A53EB4C60DECE4DEAC9` (final)
- Requires reboot to load

### Bugs Fixed

| Bug | Symptom | Fix |
|-----|---------|-----|
| Header path | `#include "nfs_multipath.h"` not found in kernel build | Inline struct declarations |
| IS_ENABLED guard | `IS_ENABLED(CONFIG_NFS_MULTIPATH)` evaluates false | `ccflags-y += -DCONFIG_NFS_MULTIPATH` |
| Static conflict | `static` in nfs4proc.c vs non-static in nfs_multipath.c | Remove `static` from nfs4proc.c |
| Wrong struct | `mpath_num_xprts` in `nfs_client` not `nfs_server` | Moved to correct struct in `nfs_fs_sb.h` |
| Kernel headers | Out-of-tree build uses `/usr/src/` headers | Copy patched header to kernel headers dir |
| Idle transports | Multipath transports created but unused by SunRPC | Direct `tk_xprt` assignment in pagelist.c |
| Small-read flooding | 16 mirrors for every 1MB read overwhelms RPC layer | Size threshold: `bytes >= N × rsize` |

---

## Java / dCache Changes

### `FileRepositoryChannel.java`
- Added `_transferBufferSize` (int) and `_transferConcurrency` (int) fields
- New constructor: `FileRepositoryChannel(Path, Set, int bufferSize, int concurrency)`
- `transferTo()` routes to:
  - `transferToSequential()` when concurrency ≤ 1 (original 1MB buffered loop)
  - `transferToPipelined()` when concurrency > 1 (async pipeline)

The async pipeline uses `AsynchronousFileChannel.read()` with N concurrent
outstanding reads at different file offsets, feeding a sequential
`WritableByteChannel.write()` in order.

### `FlatFileStore.java`
- Added `_transferBufferSize` field
- Updated `openDataChannel()` to pass buffer size

### `pool.xml`
- Wired `pool.backend.transfer-buffer-size` through Spring `byteSizeParser` bean

### `pool.properties`
- New property: `pool.backend.transfer-buffer-size = 1 MiB`

### Benchmark Tools

| Class | Purpose | Best Result |
|-------|---------|------------|
| `MR` | Max read (32 streams, 8 pools, 16 async) | 198 Gb/s |
| `BS` | N-open FileChannel, same file | 2,245 MB/s |
| `Xfer16` | Dual-NIC 16-stream cross-machine | 89 Gb/s |
| `VX2` | Async write pipeline with verification | 78 Gb/s (640GB, 0 errors) |
| `WriteTest` | Local NFS write throughput | 86 Gb/s |
| `AsyncPipe` | Generic async read pipeline | 11.4 GB/s |
| `DualXfer` | 32-stream cross-machine | 89 Gb/s send / 63 Gb/s recv |

---

## Policy Routing

```mermaid
flowchart TD
    PKT[Outbound packet] --> SRC{Source IP?}
    SRC -->|fc07:2::1:a:22| T100["Table 100<br/>→ storagea.1001"]
    SRC -->|fc07:2::2:a:22| T200["Table 200<br/>→ storageb.1001"]
    T100 --> SWA[CE6866a]
    T200 --> SWB[CE6866b]
```

```bash
# /etc/iproute2/rt_tables
100 storagea
200 storageb

# Per-table routes
ip -6 route add fc07:2::/64 dev storagea.1001 table 100
ip -6 route add fc07:2::/64 dev storageb.1001 table 200

# Policy rules
ip -6 rule add from fc07:2::1:a:22 table 100 pref 100
ip -6 rule add from fc07:2::2:a:22 table 200 pref 100
```

Without this, all traffic uses storagea.1001 (lower metric). With it:
- Source IP `fc07:2::1:a:22` → storagea.1001 → CE6866a
- Source IP `fc07:2::2:a:22` → storageb.1001 → CE6866b

---

## Mount Configuration

| Mount | Server IP | Export | Options |
|-------|----------|--------|---------|
| `/dcache/pool1` | `fc07:2::11` | `/dCache` | `vers=3,nconnect=16,rsize=1M,wsize=1M,hard,noatime,proto=tcp6` |
| `/dcache/pool2` | `fc07:2::12` | `/dCache` | same |
| `/dcache/pool3` | `fc07:2::13` | `/dCache` | same |
| `/dcache/pool4` | `fc07:2::14` | `/dCache` | same |
| `/dcache/pool5` | `fc07:2::15` | `/dCache` | same |
| `/dcache/pool6` | `fc07:2::16` | `/dCache` | same |
| `/dcache/pool7` | `fc07:2::17` | `/dCache` | same |
| `/dcache/pool8` | `fc07:2::18` | `/dCache` | same |

Total: 8 mounts × 16 nconnect = 128+ TCP connections.

---

## Key Architectural Decisions

```mermaid
flowchart TD
    Q1{NFSv3 or v4.1?} -->|v3| D1[No sessions<br/>No stateids<br/>No trunking failures]
    Q1 -->|v4.1| X1[Clientid mismatch<br/>on OceanStor<br/>multipath blocked]
    
    Q2{Multipath approach?} -->|8 mounts| D2[Simple, reliable<br/>Per-controller targeting<br/>Proven by eNFS]
    Q2 -->|Kernel mesh| X2[Transports created<br/>but SunRPC dispatch<br/>only uses primary]
    
    Q3{I/O parallelism?} -->|Userspace async| D3[16 concurrent reads<br/>per stream<br/>AsynchronousFileChannel]
    Q3 -->|Kernel striping| X3[Mirror count override<br/>works for large reads<br/>overwhelms small reads]
    
    Q4{Routing?} -->|Policy routing| D4[Source-based tables<br/>Deterministic NIC selection]
    Q4 -->|Host routes| X4[/128 routes lost<br/>after reboot]
    
    style D1 fill:#ccffcc
    style D2 fill:#ccffcc
    style D3 fill:#ccffcc
    style D4 fill:#ccffcc
    style X1 fill:#ffcccc
    style X2 fill:#ffcccc
    style X3 fill:#ffcccc
    style X4 fill:#ffcccc
```

---

## Remaining Work

1. **Write speed**: NFSv3 writes at 86 Gb/s local, 78 Gb/s remote.
   Reads are 2.3× faster. Mitigation: write to different inodes per stream,
   use `wsize` tuning, client-side write coalescing.

2. **Kernel striping**: Threshold requires >16MB reads. Small reads (dd, fio)
   don't benefit. Add progressive mirror count based on request size.

3. **Switch monitoring**: Telegraf + Grafana ready on diskpoolmgmt.
   Switch SNMPv3 partially configured — VTY session management needed.

4. **dCache DEB rebuild**: Async transferTo() in source but not in deployed DEB.
   Build container `/opt/dcache` needs re-clone and full build.

---

## Git State

| Item | Value |
|------|-------|
| **Tag** | `v0.2.0` |
| **Branch** | `main` |
| **Repository** | https://github.com/darrenstarr/dnfs |
| **Key commit** | `29191af` — Stage 2 striping patches |
