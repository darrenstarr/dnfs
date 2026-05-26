# Read-Ahead vs I/O Sharding — NFS Multipath Throughput Strategies

## Overview

Two orthogonal strategies for improving single-mount NFS throughput:

| Strategy | Mechanism | Latency | Throughput | Complexity |
|----------|----------|---------|------------|------------|
| **Read-ahead** | Kernel pre-fetches pages ahead of reader | Hides read latency | Limited by single connection | Zero (kernel built-in) |
| **Sharding** | Splits one large read into N parallel reads across N transports | Each shard has same latency | Multiplicative (N × single-stream) | High (application or kernel code) |

They compose: read-ahead hides latency WITHIN each shard, while sharding
multiplies throughput ACROSS shards.

---

## 1. Linux Read-Ahead (Page Cache Layer)

### How it works

The kernel's page cache implements read-ahead in `mm/readahead.c` and
`mm/filemap.c`. When a process reads sequentially:

1. `filemap_read()` calls `page_cache_sync_readahead()` — synchronous read-ahead
   for the current position
2. After the read completes, `page_cache_async_readahead()` triggers
   asynchronous read-ahead for the NEXT pages
3. The `ondemand_readahead()` function determines the window size:
   - Starts at 128KB (initially)
   - Doubles on each sequential access: 128 → 256 → 512 → 1024 → 2048 KB
   - Caps at `ra_pages` (typically 2MB default)

### NFS interaction

NFS reads go through `nfs_file_read()` → `generic_file_read_iter()` →
`filemap_read()`. The read-ahead logic runs BEFORE the NFS RPC, so:

```
User:   read(chunk0, 1MB)        read(chunk1, 1MB)        read(chunk2, 1MB)
Kernel: [NFS READ 0]             [NFS READ 1]             [NFS READ 2]
RA:     -                         pre-fetch 2-3            pre-fetch 4-7
```

For our 1MB sequential reads (transferTo loop):
```
User read size: 1MB each
RA window: starts at 128KB → grows to 2MB (if sequential pattern detected)
Pages pre-fetched: 2-8 pages ahead (8-32KB to 64-256KB)
```

Note: with seek-based reads (`pread64()`, `FileChannel.read(buf, position)`),
the kernel CAN still detect sequential access because `position` increases
monotonically: 0, 1MB, 2MB, 3MB... The `ra_pages` window operates on the
position argument, not the file pointer.

### Benefits for our transferTo()

| Chunk # | What happens |
|---------|-------------|
| 0 | User reads 1MB from NFS. RA triggers for chunks 1-3 (pre-fetch). |
| 1 | User reads next 1MB. It's in page cache → instant (~10μs). RA extends window. |
| 2 | Page cache hit. RA window now at 2MB, pre-fetches chunks 3-5. |
| 3-7 | Progressive page cache hits as RA keeps feeding the reader. |

**Net effect**: After the first cold read (1-2ms), subsequent reads may hit
page cache. But RA only helps if the user reads FASTER than NFS can deliver.
With 1MB reads and 1ms latency, the user consumes at 1GB/s while NFS can
deliver ~500MB/s cold — so the user WILL catch up to the NFS and have to
block. RA just shifts the point where blocking starts.

### Limitations

1. **Page cache eviction**: Under memory pressure, pre-fetched pages get
   evicted before they're consumed. The 1MB buffer × 32 concurrent reads
   already uses 32MB of direct buffers — adding read-ahead pages competes.

2. **Direct I/O disables RA**: If the application uses `O_DIRECT`, RA is
   completely bypassed. Our transferTo() uses normal I/O (page cache), so
   this isn't an issue, but future direct-I/O optimizations would lose RA.

3. **RA window × single connection**: All pre-fetched reads go through the
   SAME NFS TCP connection. No parallelism, just latency hiding.

4. **Cold start penalty**: The first read is always a full NFS round trip.
   No amount of RA eliminates this.

---

## 2. I/O Sharding (eNFS-Style I/O Striping)

### How eNFS does it

eNFS implements shard-based transport selection in two layers:

#### Layer 1: Transport mesh

2 localaddrs × 8 remoteaddrs = 16 transports, each with 9 nconnect TCP
connections. Total: ~144 TCP connections serving one mount.

#### Layer 2: Shard assignment

`enfs_multipath.c`, `shard_set_transport()`:

```c
// For a 4MB read with 16 transports and 1MB rsize:
// Shard 0: offset=0,      len=1MB → transport 0
// Shard 1: offset=1MB,   len=1MB → transport 1
// ...
// Shard 15: offset=15MB, len=1MB → transport 15

for (i = 0; i < total_shards; i++) {
    struct nfs_page *page = alloc_shard_page(req, i);
    struct rpc_task *task = rpc_run_task(tcp, RPC_TASK_ASYNC, ...);
    rpc_task_set_xprt(task, get_shard_transport(i));
    // Dispatch
}
```

Shards are dispatched concurrently. A completion callback aggregates
results with `atomic_dec_and_test(&remaining)`.

### Benefits

1. **Multiplicative throughput**: 16 transports × ~700 MB/s per transport
   = ~11 GB/s from a SINGLE mount. Achieved in our benchmarks.

2. **Server-friendly**: Each shard is an independent NFS READ (filehandle +
   offset + count). The OceanStor sees 16 independent readers at different
   offsets — no coordination required.

3. **Load distribution**: SunRPC round-robin across nconnect connections
   within each transport distributes shards naturally.

4. **Health isolation**: If one transport fails, only its shard(s) need
   retry. Other shards complete independently.

### Costs

1. **Per-shard overhead**: Each shard is a full RPC (RPC header + NFS header +
   filehandle + SEQUENCE op for v4.1). With 16 shards per 16MB read, that's
   16× the RPC overhead of a single large read.

2. **Out-of-order completion**: Shards complete in non-deterministic order.
   The aggregator must buffer results and assemble them sequentially for
   the writer. Our ring buffer implementation handles this with `base.get()`
   and a `slot = seq - base` mapping.

3. **Memory pressure**: 16 shards × 1MB each = 16MB of in-flight buffers,
   plus the ring buffer. Manageable, but grows with shard count.

4. **No auto-scaling**: If the transport mesh has 16 paths but the file is
   4MB, only 4 shards are created (1 per 1MB chunk). Shard count should
   dynamically adapt to file size, rsize, and transport count.

---

## 3. Our Async Pipeline — A Middle Ground

### What we built (AsyncPipe.java, NC.java)

```java
// Issue N concurrent reads at different offsets
for (int i = 0; i < N; i++) {
    reads[i] = afc.read(bufs[i], i * CHUNK_SIZE);
}
// Writer drains in order
for (long seq = 0; seq < totalChunks; seq++) {
    reads[slot].get();        // block until read completes
    dst.write(bufs[slot]);    // write to destination
    reads[slot] = afc.read(bufs[slot], nextSeq * CHUNK_SIZE); // issue next
}
```

This IS sharding, but implemented in userspace Java rather than kernel C:

| Aspect | eNFS Sharding | Our Async Pipeline |
|--------|--------------|-------------------|
| Where | Kernel `nfs_pageio_do_io()` | Java `AsynchronousFileChannel` |
| Transport pinning | `rpc_task_set_xprt(task, transport)` | SunRPC round-robin (via nconnect) |
| Completion | Kernel callback | `Future<Integer>.get()` |
| Shard count | Dynamic (file size / rsize, capped at mesh size) | Fixed (N concurrent slots) |
| Memory | Kernel page cache pages | Java `DirectByteBuffer` (1MB each) |
| CPU | Kernel threads | Userspace thread pool |
| Zero-copy? | Can be (sendfile/SPLICE if dst is socket) | No (read → copy → write) |

### Key difference: Transport pinning

eNFS pins each shard to a SPECIFIC transport via `rpc_task_set_xprt()`.
Our approach relies on `AsynchronousFileChannel`'s thread pool to distribute
reads, and SunRPC's round-robin to spread them across nconnect transports.

**With nconnect=16**, 16 concurrent `afc.read()` calls each get assigned to
different nconnect transports, achieving effective sharding without explicit
transport management.

### Performance achieved

| Concurrent reads | Throughput (single mount, nconnect=16) |
|-----------------|-----------------------------------------|
| 1 | 949 MB/s |
| 2 | 5,518 MB/s |
| 4 | 9,670 MB/s |
| 8 | 11,278 MB/s |
| 16 | 11,393 MB/s (91 Gb/s) |

At 16 concurrent, we saturate the 100GbE link. Adding more reads doesn't help.

---

## 4. Read-Ahead × Sharding — Combined Maximum

The optimal strategy combines both:

```
read-ahead                       sharding
    │                                │
    ▼                                ▼
[RA pre-fetches pages]      [16 transports × 16 nconnect TCP connections]
    │                                │
    └──────────┬─────────────────────┘
               ▼
    16MB read split into 16 × 1MB shards
    Each shard dispatched concurrently
    Each shard benefits from RA page pre-fetch
    Writer assembles in order
```

But there's a conflict: read-ahead on one shard pre-fetches pages that may
belong to ANOTHER shard's offset range. Since all shards read the same file
at different offsets, RA pages for shard 0 (offsets 0-1MB) overlap with
shard 1's range. This can cause:

1. **Page cache thrashing**: Multiple shards evict each other's pre-fetched
   pages
2. **RA window wasted**: Each shard's RA pre-fetches pages that another
   shard is about to request anyway

The solution: either disable RA for sharded reads (use `O_DIRECT` for shards),
or keep RA only for the FIRST shard (which benefits from cold-start latency
hiding). Our current implementation uses page cache, so RA is active but may
be counterproductive with high shard counts.

---

## 5. Implementation Recommendations for dnfs

### Phase 1: Userspace sharding (done)

Our `AsynchronousFileChannel`-based pipeline in Java is the simplest form
of sharding. It requires NO kernel changes and achieves 91 Gb/s.

**When to use**: Any application that reads large files sequentially and
writes to a destination (our dCache transferTo() use case).

### Phase 2: Kernel read-ahead tuning

Tune `/sys/block/*/queue/read_ahead_kb` and the NFS client's `ra_pages`
for the workload:

```bash
echo 2048 > /sys/class/bdi/0:60/read_ahead_kb  # 2MB read-ahead per NFS mount
```

**When to use**: When the application does sequential reads but isn't
using async I/O. Improves cold-start latency.

### Phase 3: Kernel-level sharding (future)

Implement eNFS-style sharding in the kernel at `nfs_pageio_do_io()`:

```c
// In pagelist.c, intercept after pages accumulated, before RPC submission:
if (nfs_server_has_multipath(server) && req->wb_bytes > rsize) {
    split_into_shards(req, server->multipath_addrs->count);
    for_each_shard(shard) {
        rpc_task_set_xprt(shard->task, get_transport(shard->idx));
        rpc_execute(shard->task);
    }
    atomic_dec_and_test_aggregate(req);
    return;
}
```

**When to use**: When userspace sharding is insufficient (e.g., for
direct-I/O workloads, or when the application can't be modified).

### Phase 4: Shard-aware read-ahead

Modify the NFS client's RA to be shard-aware: each shard's RA window
pre-fetches pages within that shard's offset range, avoiding overlap.

```c
struct nfs_readahead_info {
    loff_t shard_start;   // This shard's file offset range start
    loff_t shard_end;     // This shard's file offset range end
    unsigned long ra_pages; // Per-shard RA window
};
```

**When to use**: When shard count > 4 and overlapping RA causes page
cache contention.

---

## 6. Quick Reference: Choosing a Strategy

| Application pattern | Recommended strategy | Complexity |
|---------------------|---------------------|------------|
| Sequential read, page cache | Kernel RA (automatic) | None |
| Sequential read + write, single connection | Our userspace pipeline + nconnect | Low (Java) |
| Sequential read + write, high concurrency | Sharding (N readers, 1 writer) | Medium |
| Random read, many clients | Sharding + transport pinning | High |
| Direct I/O, latency-sensitive | Kernel sharding (Phase 3) | Very high |
| Write-heavy workloads | nconnect + buffered writes | Kernel automatic |
