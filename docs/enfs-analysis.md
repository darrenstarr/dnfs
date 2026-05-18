# eNFS vs dnfs — Multipath Transport Architecture Analysis

Based on inspection of the unmodified Huawei eNFS codebase at
https://github.com/darrenstarr/huaweienfs, specifically the OpenEuler
kernel patches in `vendor/openeuler/fs/nfs/enfs/` and
`patches/ubuntu-7.0/`.

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

### How dnfs creates transports

Our hook in `nfs4proc.c` (or patch 0006 in `nfs4client.c`):

```c
// Iterates ONLY remoteaddrs, no local binding
for (i = 1; i < list->count; i++) {
    struct xprt_create xprtargs = {
        .dstaddr = &list->addrs[i],  // remote only
        // .srcaddr = NULL           // kernel picks source
    };
    rpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL);
}
```

**Result**: One transport per remote IP, kernel picks source address
(default route → always the same NIC).

### Impact on switch LACP entropy

CE6866 default LACP hash: `{src-mac, dst-mac, src-ip, dst-ip, src-port, dst-port, protocol}`

| | dnfs (1 transport/IP) | eNFS (full mesh) |
|---|---|---|
| Source MACs in use | 1 (same NIC) | 2 (both NICs) |
| Source IPs in use | 1 (default) | 2 (both IPs) |
| Unique hash permutations | ~8 | ~16+ |

eNFS produces traffic on ALL source/destination link permutations because
each transport is pinned to a specific local interface. Our traffic
collapses onto one NIC unless we manually configure host routes.

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

Our approach passes `NULL` for setup, so transports are added
immediately. The session trunking check then kicks them out.

## 3. NFSv3 Only — How eNFS Avoids the Session Trunking Problem

`enfs_multipath.c:925`:

```c
void enfs_create_multi_xprt(struct rpc_create_args *args, struct rpc_clnt *clnt)
{
    if (args->version == 4)
        return;    // NFSv4 multipath NOT SUPPORTED
    // ... v3-only code ...
}
```

eNFS is NFSv3-only. NFSv3 has:
- No sessions → no `SEQUENCE` op → no session ID to validate
- No `EXCHANGE_ID` → no clientid assignment
- No trunking detection → no clientid mismatch failures

Each transport is an independent TCP connection carrying independent
NFSv3 RPCs. The server doesn't care that they share a mount.

## 4. Separate Loadable Module Architecture

eNFS uses a **two-adapter** design:

| Layer | File | Compiled into | Purpose |
|-------|------|---------------|---------|
| nfs_adapter | `enfs_adapter.c` | `nfs.ko` | Adds mount option parsing + hooks in client.c, super.c, fs_context.c |
| rpc_adapter | `sunrpc_enfs_adapter.c` | `sunrpc.ko` | Adds 5 hook sites in clnt.c (create_clnt, release, set_transport, queue accounting) |
| enfs module | `enfs.ko` (20+ files) | Separate loadable module | Full mesh creation, path-ping, shard queries, failover, remount |

This is 3-patch series + standalone module. Our approach is simpler:
compile everything into `nfs.ko` with 6 patches.

## 5. Additional eNFS Features We Lack

| Feature | eNFS location | Our status |
|---------|--------------|------------|
| Path-ping health checks | `enfs_multipath.c` `pm_ping_rpc_test_xprt` | Not implemented |
| Shard-based transport selection | `shard_set_transport()` | Not implemented |
| DNS rebinding for remoteaddrs | `enfs_dns_resolve.c` | IP literals only |
| Live remount with new IP lists | `enfs_remount.c` | Not implemented |
| Global transport cap (512 links) | `enfs.h` `DEFAULT_ENFS_MAX_LINK_COUNT` | Not implemented |
| `/proc/enfs/` runtime interface | `enfs_proc.c` | Not implemented |
| NFSv3 EXTEND operation (shard info) | `nfs3xdr.c` patches | NFSv3 not targeted |
| Failover with state machine | `enfs_failover.c` | Stock SunRPC reconnect |
| Configuration via `enfs.config.ini` | `enfs_config.c` | Mount options only |

## 6. Connection Count Limits

| Parameter | eNFS Value | Our Value |
|-----------|-----------|-----------|
| Transports per mount | 31 (default, configurable) | 9 (nconnect cap) |
| Unique local addrs | 8 (hardcoded) | Unlimited (parsed, unused) |
| Remote addrs | 32 (configurable) | 32 (hardcoded) |
| Global transport cap | 512 (configurable) | None |
| Max mounts | 256 | Unlimited |

## 7. Files Modified

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

### dnfs (6 patches)

```
fs/nfs/{Kconfig,Makefile,internal.h,fs_context.c,client.c,
        super.c,nfs4client.c,nfs_multipath.c}         — all in nfs.ko
```

No SunRPC changes, no separate module, no include/linux changes.
