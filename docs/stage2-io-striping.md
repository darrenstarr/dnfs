# Stage 2: Client-Side I/O Striping (Single-Stream Pipelining)

## Problem

Stage 1 creates multiple TCP transports and relies on SunRPC round-robin dispatch
to distribute NFS *operations* across links. This works for concurrent workloads
(many small files, many threads) but fails for single-stream throughput:

- A single `dd bs=1M` or sequential `fio` read sends one 1MB READ RPC
- That RPC is dispatched to a single transport
- One 100Gb/s link caps at ~12.5 GB/s (after TCP/Ethernet/IP overhead)
- The second 100Gb/s link sits idle

Target: **~20 GB/s** aggregate through a single file descriptor across 2x100Gb/s.

## Solution Overview

Split a single large NFS READ or WRITE operation into multiple **stripes** — each
stripe is a sub-range of the original request, issued concurrently on different
transports, with results reassembled in page cache before VFS completion.

```
                  ┌──────────────────────────────────────┐
VFS read() 4MB ──►│  nfs_pageio_stripe()                 │
                  │                                      │
                  │  Stripe 0: [0..1MB)  → transport A   │
                  │  Stripe 1: [1MB..2MB) → transport B   │
                  │  Stripe 2: [2MB..3MB) → transport A   │
                  │  Stripe 3: [3MB..4MB) → transport B   │
                  │                                      │
                  │  wait_all() → reassemble → complete   │
                  └──────────────────────────────────────┘
```

This is **not pNFS**. No server layout, no device info, no `GETDEVICEINFO`.
The server sees normal NFSv4.1 READ/WRITE ops arriving on different TCP
connections carrying the same session ID. Standard NFSv4.1 semantics
(NFS4ERR_BAD_STATEID, delegation recalls, lease renewal) are preserved.

## Design Decisions

### 1. Stripe at the pageio layer, not the RPC layer

NFS already has a two-phase I/O pipeline: `nfs_pageio_add_request()` accumulates
pages into a coherent `nfs_pgio_header`, then `nfs_generic_pgio()` issues one RPC
for the entire header.

We intercept *after* page accumulation (when we know the full byte range) and
*before* the RPC is issued. This gives us:
- Full byte range for stripe calculation (offset + count known)
- Page descriptors already allocated and locked
- The right place to create sub-headers without duplicating the pageio logic

### 2. Stripe size = rsize/wsize (negotiated per-session)

Each stripe is one `rsize`/`wsize` chunk. For a 4MB read with rsize=1MB and
2 transports, we issue four 1MB reads. For a 5MB read, five 1MB reads.

Rationale: the max read/write size is the natural RPC granularity. Smaller
stripes increase RPC overhead; larger stripes leave transports idle.

### 3. Stripe-to-transport binding: round-robin or shortest-queue

**Round-robin** (simple, predictable): stripe i → transport i % ntransports.

**Shortest-queue** (better utilization): stripe → transport with fewest
outstanding bytes. Preferred when links have different speeds or some
transports are shared with other mounts.

Implementation: use `rpc_task::tk_xprt` pinning via `rpc_task_set_xprt()`
to bind each sub-RPC to a specific transport.

### 4. Error handling: fail-fast with retry on the same transport

If a single stripe fails with a recoverable error (timeout, connection reset,
`NFS4ERR_DELAY`), retry that stripe on the *same* transport. If it fails
permanently, fail the entire compound I/O. We do NOT reassign a failed stripe
to another transport — the striping assignment is fixed per-I/O.

Rationale: reassigning stripes mid-I/O creates ordering complexity with
writes and doesn't help if the error is server-side (e.g., `NFS4ERR_ACCESS`).

### 5. Write striping: must flush to stable storage atomically

NFSv4.1 UNSTABLE writes followed by a COMMIT are the standard pattern.
Striped writes:
- Issue N UNSTABLE WRITE calls across transports
- Wait for all WRITEs to complete
- Issue a single COMMIT on *one* transport (the primary)
- COMMIT covers the full byte range

If a COMMIT fails, all sub-writes must be retried. This is complex — the
safe approach is to **serialize the COMMIT after all WRITEs complete**
and use the standard `pnfs_layoutcommit` callback model (used for pNFS).

For initial implementation, write striping can be **opt-in** with a mount
option (`stripe_write=1`) or deferred to a later patch.

## Architecture: Page-Level Staging

### Data Flow

```
nfs_readpages / nfs_readahead / nfs_read_folio
  │
  ├─► nfs_pageio_add_request()   ← accumulate pages (unchanged)
  │
  ▼
nfs_pageio_do_io() — NEW INTERCEPT
  │
  │   struct nfs_pgio_header *hdr = pageio->pg_list
  │   int ntransports = xprt_switch_count(hdr->xprt_switch)
  │
  ├─► ntransports <= 1  OR  hdr->count < threshold?
  │       → fall through to nfs_generic_pgio() (original path)
  │
  ▼
nfs_pageio_stripe_submit(hdr, ntransports, stripe_size)
  │
  ├─► For each stripe (offset, len):
  │     sub_hdr = nfs_pgio_header_clone(hdr, offset, len, transport_idx)
  │     sub_hdr->completion_ops = nfs_stripe_completion_ops
  │     nfs_initiate_pgio(rpc_clnt, sub_hdr, cred, ...)
  │
  ├─► Wait for all sub_headers to complete (completion counter)
  │
  ▼
nfs_stripe_done()
  │
  ├─► If all stripes ok:
  │     copy sub_hdr stats into parent hdr (res, fattr, etc.)
  │     hdr->completion_ops->completion(hdr)  ← original callback
  │
  ├─► If any stripe failed:
  │     hdr->error = sub_error
  │     hdr->completion_ops->completion(hdr)  ← caller handles error
  │
  └─► Free sub_headers
```

### Key Data Structures

```c
/* Per-I/O striping context, stored in nfs_pgio_header::stripe */
struct nfs_stripe_context {
    struct nfs_pgio_header  *parent;     /* original header */
    struct nfs_pgio_header  **stripes;   /* array of sub-headers */
    unsigned int             nstripes;
    atomic_t                 remaining;  /* stripes not yet complete */
    int                      error;      /* first error seen */
    struct completion        done;
};

/* Threshold below which striping is not attempted */
#define NFS_MIN_STRIPE_SIZE    (256 * 1024)  /* 256KB */
```

### Transport Selection Policy

```c
/* Transport selector: picks xprt for stripe i of N */
struct rpc_xprt *nfs_pick_stripe_xprt(struct rpc_clnt *clnt,
                                       int stripe_idx,
                                       int ntransports)
{
    struct xprt_switch *xps;

    rcu_read_lock();
    xps = rcu_dereference(clnt->cl_xpi.xpi_xpswitch);

    /* Round-robin: stripe i → xprt[i mod ntransports] */
    int xprt_idx = stripe_idx % ntransports;
    struct rpc_xprt *xprt = xprt_switch_get_xprt_by_index(xps, xprt_idx);

    rcu_read_unlock();
    return xprt;
}
```

The `xprt_switch` already maintains a linked list. We add a helper to get the
Nth entry. Each sub-RPC task pins its transport via `tk_xprt`.

### Sub-Header Memory Management

We need `nfs_pgio_header` clones for each stripe. The header is normally
allocated from a slab cache and embedded in a larger allocation
(`nfs_pgio_data` or `nfs_pageio_descriptor`). Options:

**Option A: Allocate H sub-headers from slab** — `nfs_pgio_header_alloc()`
with `nfs_pageio_stripe_ops` callbacks. Clean, uses existing infrastructure.
Overhead: H-1 extra allocations per I/O.

**Option B: Pre-allocate stripe headers in the parent header** — extend
`nfs_pgio_header` with an `nstripes_inline` array. Zero extra allocations
for the common case. Constrains max stripes to a compile-time constant.

**Recommendation: Option A** for flexibility, then inline optimization
if profiling shows slab pressure. A 4MB read with rsize=1MB on 2 transports
means 4 headers instead of 1 — well within slab cache margins.

### Integration with NFS Page Cache

NFS page I/O uses these entry points:
- `read_pagelist()` — issues READs from `nfs_pageio_descriptor` pages
- `write_pagelist()` — issues WRITEs
- `pg_test()` — coherence test (can pages share a header?)

Striping integrates at `nfs_pageio_do_io()` — the single point where the
accumulated page list is converted to a pgio header and submitted. We add a
check after `nfs_pageio_add_request()` finishes accumulation:

```c
/* In fs/nfs/pagelist.c, nfs_pageio_do_io() */
static void nfs_pageio_do_io(struct nfs_pageio_descriptor *desc)
{
    struct nfs_pgio_header *hdr;
    ...
    hdr = nfs_pgio_header_alloc(desc);
    ...
    if (nfs_multipath_can_stripe(hdr))
        nfs_pageio_stripe_submit(hdr);
    else
        nfs_generic_pgio(hdr);
}
```

### Compatibility with Delegations, Leases, State

**No changes needed.** Striped operations share the same `nfs_client`,
session ID, slot table, and stateid. The server sees them as concurrent
operations from the same client — this is already supported by NFSv4.1
session semantics. `SEQUENCE` operations carry the session ID and slot
sequence number independently per transport.

**Delegation recall**: If a delegation is recalled mid-stripe, the server
returns `NFS4ERR_RECALL_DELEG` on in-flight operations. The client's
delegation return code (already in `nfs4proc.c`) handles this — our stripe
completion callback propagates the error to the parent.

### Session Slot Management

Each sub-RPC uses a separate SEQUENCE slot from the session slot table.
With a typical slot table size of 64+:

- 2 transports × 4 stripes = 8 slots in use concurrently
- Slot exhaustion is not a concern for reads (ordered, no COMMIT needed)
- For writes, the COMMIT consumes an additional slot

The existing slot recovery (NFS4CLNT_SESSION_RESET) handles slot drain
correctly — all sub-RPCs use the same session and will drain together.

### Locking and Concurrency

- Stripe sub-headers share parent header's page list (by reference)
- Each stripe owns a disjoint byte range → no page-level write conflicts
- Completion is signaled via `atomic_dec_and_test(&stripe->remaining)`
- The parent header controls the final completion callback

Thread safety: the caller holds `inode->i_lock` during pageio setup.
Sub-headers are submitted asynchronously via `nfs_initiate_pgio()` which
takes its own references. The stripe done callback fires from RPC reply
processing (workqueue context), not under the inode lock.

### Configuration

```c
/* Kernel config: CONFIG_NFS_MULTIPATH enables striping infrastructure */
#if IS_ENABLED(CONFIG_NFS_MULTIPATH)
    bool nfs_multipath_can_stripe(struct nfs_pgio_header *hdr);
    void nfs_pageio_stripe_submit(struct nfs_pgio_header *hdr);
#endif
```

**Mount options** (add to `fs_context.c` enum/table):
- `stripe=0|1` — enable/disable striping (default: 1 when ntransports ≥ 2)
- `stripe_min=N` — minimum bytes before striping activates (default: 256K)
- `stripe_policy=rr|lq` — round-robin or least-loaded transport (default: rr)

### Files Modified

| File | Change |
|------|--------|
| `fs/nfs/pagelist.c` | `nfs_pageio_do_io()` intercept + `nfs_pageio_stripe_submit()` |
| `fs/nfs/nfs_multipath.c` | Transport counting, stripe policy, `nfs_multipath_can_stripe()` |
| `fs/nfs/internal.h` | Stripe context struct + function declarations |
| `fs/nfs/fs_context.c` | Parse `stripe=`, `stripe_min=`, `stripe_policy=` mount options |
| `fs/nfs/nfs4proc.c` | (maybe) stripe-aware COMMIT for writes |

### Files NOT Modified

`nfs4xdr.c`, `nfs4state.c`, `nfs4session.c`, `client.c`, `super.c`, `write.c`,
`read.c`, `inode.c` — no protocol or state changes needed. The SunRPC layer
(`net/sunrpc/`) is untouched.

### Implementation Order

1. **Phase 2a — Transport index lookup**: Add `xprt_switch_get_xprt_by_index()` to SunRPC
2. **Phase 2b — Read striping**: Split reads across transports, no write path yet
3. **Phase 2c — Sub-header allocation**: Clone+submit for stripes
4. **Phase 2d — Completion aggregation**: Stripe done callback → parent completion
5. **Phase 2e — Mount options**: `stripe=`, `stripe_min=`, `stripe_policy=`
6. **Phase 2f — Write striping**: UNSTABLE WRITE + single COMMIT pattern
7. **Phase 2g — Error injection tests**: Simulate transport failure mid-stripe

### Expected Throughput

| Configuration | Single-stream read | Multi-stream read |
|---------------|-------------------|-------------------|
| Stage 1 (no striping) | ~12.5 GB/s (1 link) | ~20 GB/s (round-robin across operations) |
| Stage 2 (striping) | ~20 GB/s (2 links) | ~20 GB/s |

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Server rejects striped operations (session-per-connection enforcement) | Detect `NFS4ERR_BAD_SESSION` on non-primary transport → fall back to primary-only |
| Stripe imbalance (one link slower) | Least-loaded policy, or adaptive stripe size based on per-transport RTT |
| Memory pressure from extra sub-headers | Cap concurrent stripes to `ntransports * 4`; use slab shrinker |
| Server-side locking contention on overlapping byte ranges (writes) | Writes use non-overlapping byte ranges by construction; no extra server locks |
| Out-of-order stripe completion breaks read consistency | NFS READs are idempotent by offset; any order is correct |

### Relationship to pNFS

This feature is **complementary** to pNFS, not a replacement. pNFS requires
server layout support (files/flexfiles/block) and provides block-level striping
to data servers. Our striping is transport-level only — same MDS, different
TCP connections. When both are present, pNFS takes priority for layout-based I/O,
and our transport striping handles MDS operations (metadata, small I/O, fallback
when no layout is held).
