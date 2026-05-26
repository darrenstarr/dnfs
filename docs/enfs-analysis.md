# eNFS vs dnfs — Multipath Transport Architecture Analysis (Updated for NFSv3)

Based on inspection of the unmodified Huawei eNFS codebase at
https://github.com/darrenstarr/huaweienfs, specifically the OpenEuler
kernel patches in `vendor/openeuler/fs/nfs/enfs/` and
`patches/ubuntu-7.0/`.

## Both projects now target NFSv3

eNFS has always been NFSv3-only. Our v4.1 session-trunking experiment
confirmed the same conclusion:

- **Different clientids per virtual port** — The OceanStor returns unique
  `clientid` values from `EXCHANGE_ID` on each virtual port. NFSv4.1 session
  trunking (`nfs4_detect_session_trunking`) checks `clp->cl_clientid !=
  res->clientid` → fails → transports ejected.

- **NFSv3 has no sessions, no stateids, no trunking** — transports just
  work. An NFSv3 READ is simply `filehandle + offset + count` with no
  SEQUENCE op, no OPEN stateid, no EXCHANGE_ID.

Our v4.1 work validated that `nconnect=16` works and the async pipeline
achieves 11.4 GB/s single-mount, but multipath (single mount to multiple
IPs) remains blocked by the clientid mismatch.

## 1. The Full Mesh (source × destination)

### How eNFS creates transports

`vendor/openeuler/fs/nfs/enfs/enfs_multipath.c`, `enfs_combine_addr()` (line 493):

```c
// total_combinations = local_addrs_count × remote_addrs_count
// e.g., 2 localaddrs × 8 remoteaddrs = 16 transports

for (i = 0; i < total_combinations; i++) {
    local_index  = i % local_total;
    remote_index = (i + link_count / lcm) % remote_total;

    attach_infos[i].localAddress  = &local->address[local_index];
    attach_infos[i].remoteAddress = &remote->address[remote_index];

    enfs_configure_xprt_to_clnt(xprtargs, clnt, &attach_infos[i]);
}
```

`enfs_configure_xprt_to_clnt()` (line 315) binds source explicitly:

```c
xprtargs->srcaddr = (struct sockaddr *)attach_info->localAddress;
xprtargs->dstaddr = (struct sockaddr *)attach_info->remoteAddress;
rpc_clnt_add_xprt(clnt, xprtargs, enfs_add_xprt_setup, attach_info);
```

### How dnfs creates transports (NFSv3 path)

The NFSv3 hook in `nfs3client.c` (added in commit `7b96bf9`):

```c
// After nfs3_create_server() creates the primary client:
if (remotes && remotes->count > 1) {
    for (i = 1; i < remotes->count; i++) {
        xprtargs.srcaddr = &locals->addrs[i];
        xprtargs.dstaddr = &remotes->addrs[i];
        rpc_clnt_add_xprt(server->client, &xprtargs, NULL, NULL);
    }
}
```

No trunking test. No session to share. No stateid to negotiate. The transport
just gets added to the xprt_switch and starts carrying operations.

### Impact on switch LACP entropy

CE6866 default LACP hash: `{src-mac, dst-mac, src-ip, dst-ip, src-port, dst-port, protocol}`

| | dnfs (NFSv3, point-to-point) | eNFS (full mesh) |
|---|---|---|
| Source MACs in use | 2 (via host routes) | 2 (per-transport binding) |
| Source IPs in use | 2 | 2 |
| Unique hash permutations | ~16 (8 destinations × 2 sources) | ~16+ (full 2×8 mesh) |
| Per-pair connections | 1 per local→remote pair | ~9 (nconnect per pair in eNFS) |

With host routes pinning 4 IPs per NIC, dnfs achieves similar entropy to eNFS.
The key difference: eNFS binds each transport at creation time (`.srcaddr`
explicitly set), while dnfs relies on host routes for source interface selection.

## 2. Switch Control — eNFS Owns the Transport Lifecycle

eNFS does not let SunRPC auto-add transports to the switch. Instead:

1. `enfs_add_xprt_setup()` returns `1` (not 0), which tells
   `rpc_clnt_add_xprt()` to **skip** the automatic
   `rpc_xprt_switch_add_xprt()` call

2. eNFS runs path-ping on each transport before admitting it

3. Only after all transports pass health checks does eNFS call
   `enfs_xprt_switch_add_xprt()` to selectively add them

4. This prevents broken transports from polluting the switch and
   causing operation retries

Our NFSv3 approach passes `NULL` for setup, adding transports immediately.
With NFSv3, there's no trunking check to fail, so this is safe. The
transport operates immediately.

## 3. nconnect Integration

dnfs integrates with the kernel's `nconnect=` mount option for per-mount
connection parallelism:

| | Without nconnect | With nconnect=16 |
|---|---|---|
| TCP connections per mount | 2 | 16 (practical max: 9 data) |
| Single-stream read (dd) | ~500 MB/s | 956 MB/s |
| Async read pipeline (1 concurrent) | 682 MB/s | 949 MB/s |
| Async read pipeline (16 concurrent) | 10,657 MB/s | **11,393 MB/s (91 Gb/s)** |

nconnect distributes RPC operations across 16 TCP connections via SunRPC
round-robin. Combined with the NFSv3 multipath transport mesh, this
multiplies throughput without changing the transport creation code.

## 4. Additional eNFS Features We Don't Have

| Feature | eNFS location | dCache2026/dnfs status |
|---------|--------------|------------|
| Path-ping health checks | `enfs_multipath.c` `pm_ping_rpc_test_xprt` | Not implemented |
| Shard-based transport selection | `shard_set_transport()` | Not implemented |
| DNS rebinding for remoteaddrs | `enfs_dns_resolve.c` | IP literals only |
| Live remount with new IP lists | `enfs_remount.c` | Not implemented |
| Global transport cap (512 links) | `enfs.h` `DEFAULT_ENFS_MAX_LINK_COUNT` | nconnect per mount |
| `/proc/enfs/` runtime interface | `enfs_proc.c` | `/proc/self/mountstats` |
| NFSv3 EXTEND operation (shard info) | `nfs3xdr.c` patches | Not implemented |
| Failover with state machine | `enfs_failover.c` | Stock SunRPC reconnect |
| Configuration via `enfs.config.ini` | `enfs_config.c` | Mount options only |
| Separate loadable module | `enfs.ko` (20+ files) | Single `nfs.ko` patch |

## 5. Performance Comparison

### Single mount, NFSv3 multipath (predicted)

| Metric | eNFS (Huawei, production) | dnfs (our build + nconnect=16) |
|---|---|---|
| Single-stream read | ~42 Gb/s (measured) | ~8 Gb/s (dd, 1MB blocks) |
| Aggregate read (multipath) | 180 Gb/s (8 mounts, all physical links) | 130 Gb/s (8 mounts, no striping) |
| Single-mount aggregate (async pipeline) | Unknown | 91 Gb/s (16 concurrent reads) |
| Code size | 8,000+ lines (25 files) | ~200 lines (patches + multipath.c) |
| Kernel modifications | 24 patches to SunRPC + NFS | 4 patches to NFS only |
| Production readiness | Yes (shipped by Huawei) | Pre-production (testing phase) |

### Key advantages of dnfs over eNFS

1. **Simplicity** — ~200 lines vs 8,000+. No separate kernel module, no
   SunRPC modifications. Easier to review, debug, and upstream.

2. **nconnect integration** — Leverages the kernel's built-in connection
   multiplexing. Each transport in the mesh gets its own set of nconnect
   connections, multiplying aggregate throughput.

3. **Single repo** — Everything in one kernel patch series. eNFS requires
   a separate loadable module with its own build system and dependencies.

4. **NFSv4.1 compatibility** — The same `nfs_multipath.c` parser works
   for both v3 and v4.1. When/if Huawei fixes the clientid issue, the
   v4.1 path is ready to go with zero code changes.

### Key advantages of eNFS over dnfs

1. **Production-hardened** — Shipped by Huawei at scale. Path-ping,
   failover, live remount, and health monitoring are battle-tested.

2. **Full mesh binding** — Explicit local address binding per transport
   rather than relying on host routes. More deterministic traffic
   distribution.

3. **Transport admission control** — Verifies transport health before
   adding to the switch. No broken transports carrying user traffic.

4. **Shard-based I/O striping** — Distributes operations across
   transports with built-in load balancing. Not just round-robin.

## 6. Files Modified

### eNFS (24 kernel patches)

```
fs/nfs/{Makefile,Kconfig,internal.h,super.c,fs_context.c,
        nfs3xdr.c,client.c}                          — nfs_adapter hooks
net/sunrpc/{Makefile,Kconfig,clnt.c,xprt.c,
            xprtmultipath.c}                          — rpc_adapter hooks
include/linux/{nfs_fs_sb.h,nfs_xdr.h,
               sunrpc/{clnt.h,sched.h}}               — new fields
```

Plus 25 new vendor files in `fs/nfs/enfs/`.

### dnfs (4 files patched + 2 new files)

```
fs/nfs/{Kconfig, Makefile, fs_context.c, nfs3client.c}  — NFS patches
fs/nfs/nfs_multipath.c                                    — new: parser + transport creation
fs/nfs/nfs_multipath.h                                    — new: struct + API declarations
```

No SunRPC changes, no separate module, no include/linux changes.
Optionally `nfs4proc.c` for v4.1 transport creation (currently blocked
by clientid mismatch).

## 7. Verdict

For a single-endpoint deployment against the OceanStor, dnfs NFSv3 multipath +
nconnect=16 provides competitive throughput with vastly less code than eNFS.
The missing production features (path-ping, failover, live remount) are
acceptable for a focused dCache cluster where the storage network is
physically isolated and controlled.

If upstream acceptance is the goal, the NFSv4.1 path should be developed in
parallel, using the same `nfs_multipath.c` parser. When Huawei resolves the
clientid issue, the v4.1 transport creation hook in `nfs4proc.c` will activate
automatically with no additional code changes.
