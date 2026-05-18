# NFSv3 vs NFSv4.1 for Multipath — Pros/Cons Analysis

## Why NFSv3 could solve our core problems

NFSv4.1 introduced three things that block multipath on the OceanStor:

1. **Sessions + clientid** (`EXCHANGE_ID` → `CREATE_SESSION`) — every transport
   must share the same clientid to carry operations. OceanStor virtual ports
   return different clientids → session trunking fails.

2. **Stateids on READ** — every READ carries a stateid from OPEN. Without a
   valid stateid for the target client, reads fail with `NFS4ERR_BAD_STATEID`.

3. **SEQUENCE op in every COMPOUND** — adds ~48 bytes + slot ACK overhead
   to every RPC, consuming network bandwidth and CPU.

NFSv3 has NONE of these. Zero. There is no session, no stateid, no SEQUENCE.
An NFSv3 READ is:

```
RPC header + filehandle (up to 64 bytes) + offset (8) + count (4)
```

That's it. No stateid. No session. No EXCHANGE_ID. The server serves the
data and sends a reply. Done.

## Detailed Comparison

### Protocol overhead

| Aspect | NFSv3 | NFSv4.1 |
|--------|-------|---------|
| State required for READ | None — just filehandle + offset + count | OPEN stateid + SEQUENCE slot + session ID |
| State required for WRITE | None — filehandle + offset + count + data | OPEN stateid + SEQUENCE slot + session ID |
| Per-RPC overhead | ~100 bytes (RPC + NFS headers) | ~200 bytes (RPC + COMPOUND + SEQUENCE + stateid) |
| Round trips to open file | 1 (LOOKUP) | 2 (OPEN + OPEN_CONFIRM or SEQUENCE setup) |
| Concurrency model | Per-transport RPC congestion window | Per-session slot table (typically 64 slots) |

### Multipath compatibility

| Aspect | NFSv3 | NFSv4.1 |
|--------|-------|---------|
| Session trunking required | No — no sessions exist | Yes — or transports are ejected |
| Per-IP client identity | Server doesn't care | Different clientid = different server |
| State sharing across IPs | Not applicable | Stateids and clientid must match |
| Transport mesh (local × remote) | Works immediately | Blocked by clientid mismatch |
| eNFS proof of concept | **Proven** — shipped by Huawei | Not supported by eNFS |

### Features we lose

| Feature | Impact | Mitigation |
|---------|--------|-----------|
| Delegations (client caching) | More GETATTR RPCs to revalidate | Attribute cache tuning (`noac`/`actimeo`) |
| COMPOUND ops (batched RPCs) | More RPCs for metadata-heavy workloads | Our workload is bandwidth-heavy, not metadata-heavy |
| Sessions (exactly-once) | Duplicate detection lost | Retransmission-safe by design for reads |
| WRITE_PLUS / SEEK | Not available | Our workload is plain read/write |
| CLONE (server-side copy) | Must copy through client | Not used in our benchmarks |
| Named attributes | Not available | Not used |
| ACLs (rich) | POSIX draft ACLs only | Not used |
| Migration/referral | No transparent failover | Not relevant to OceanStor |
| pNFS | Required for distributed layout | pNFS doesn't work with OceanStor anyway |
| RPCSEC_GSS integrity | Weaker security | Our network is physically isolated |
| READDIRPLUS | Filehandle+attributes in one call | NFSv3 has READDIRPLUS too, server-dependent |

### Performance characteristics

| Aspect | NFSv3 | NFSv4.1 |
|--------|-------|---------|
| Per-transport max RPCs | `xprt->max_reqs` (typically 32) | Session slots (64 per session) |
| nconnect scaling | Same loop in `rpc_create()`, works identically | Same |
| Read latency (no cache) | ~1 RTT | ~1 RTT + SEQUENCE ACK overhead |
| CPU per operation | Lower (no crypto, no COMPOUND framing) | Higher (COMPOUND framing, SEQUENCE processing) |
| Throughput ceiling | Gated by RPC congestion window | Gated by session slot table |
| remoteaddrs= transport creation | No trunking test needed — just add to switch | Trunking test fails on OceanStor |

## Work Required

### Minimal NFSv3 multipath (< 100 lines)

1. Add remoteaddrs/localaddrs parsing — already done in `nfs_multipath.c` (works for both v3 and v4)
2. Add transport creation hook in `nfs3_create_server()` or `nfs3_init_client()` — same pattern as v4 but WITHOUT the session trunking dependency
3. That's it. No stateid management. No multi-nfs_client gymnastics. No session recovery edge cases.

The hook in nfs3client.c would look like:
```c
// After nfs3_create_server() creates the primary client:
if (remotes && remotes->count > 1) {
    for (i = 0; i < remotes->count; i++) {
        xprtargs.srcaddr = &locals->addrs[i];
        xprtargs.dstaddr = &remotes->addrs[i];
        xprtargs.servername = "nfs-multipath";
        rpc_clnt_add_xprt(server->client, &xprtargs, NULL, NULL);
    }
}
```

No trunking test. No session to share. No stateid to negotiate. The transport
just gets added to the xprt_switch and starts carrying operations.

### Full I/O striping for v3 (< 200 additional lines)

Same Stage 2 architecture (`docs/stage2-io-striping.md`) applies, but simpler:
- No stateid per stripe — just filehandle + offset + count
- No session slot tracking per stripe
- Each stripe is an independent RPC

## Expected throughput (NFSv3, single mount)

| | Current (v4.1, 8 mounts) | Predicted (v3, 1 mount) |
|---|---|---|
| Single-stream read | 39.5 Gb/s | 35-40 Gb/s (RPC concurrency similar) |
| Aggregate read | 180.3 Gb/s | 150-180 Gb/s (no state overhead) |
| Aggregate write | 144.3 Gb/s | 120-150 Gb/s (simpler write path) |

## Risks

1. **OceanStor NFSv3 support** — Must verify the storage serves NFSv3 on the
   same export (`/dCache`). Most enterprise arrays support both v3 and v4.

2. **readdirplus compatibility** — The v3 `READDIRPLUS` optimization may not
   be implemented by the OceanStor NFSv3 server.

3. **Attribute cache invalidation** — Without delegations, the client must
   poll the server for attribute changes. Mitigated by `acregmin/acregmax`
   mount options.

4. **No Kerberos** — The physical network isolation makes this acceptable.

5. **Upstream acceptance** — NFSv3 is legacy. A v3-only multipath patch
   may face upstream resistance. The v4.1 path is preferred for mainline.

## Verdict

NFSv3 eliminates ALL the problems introduced by NFSv4.1 sessions and
stateids. The multipath transport creation becomes trivial — no trunking
test, no stateid negotiation, no multi-nfs_client management.

The code change is < 100 lines. The performance ceiling is similar or
better (less protocol overhead per RPC). This is the path eNFS took and
it works at production scale on the OceanStor.

**Recommendation**: Implement NFSv3 multipath as an MVP. Get the
throughput numbers. If they match or exceed v4.1, ship it. The v4.1
work can continue in parallel as the "upstream target" once Huawei
fixes the clientid issue.
