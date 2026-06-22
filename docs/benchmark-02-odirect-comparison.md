# Benchmark 02: O_DIRECT Comparison — NFS vs DPC

**Date:** 2026-06-22  
**Method:** Java `FileChannel` with `ExtendedOpenOption.DIRECT`, aligned `DirectByteBuffer`  
**Page Cache:** Dropped via `echo 3 > /proc/sys/vm/drop_caches` before each test  
**Test Size:** 2048 MB, 1 MiB IO blocks

## Results

| Platform | Write (MB/s) | Read (MB/s) | Notes |
|----------|-------------|------------|-------|
| NFSv4.1 (diskpool01) | **140** | **556** | DirectByteBuffer aligned to 1 MiB for NFS block size |
| DPC (diskpool02) | **4623** | **2889** | DirectByteBuffer aligned to 4 KiB |
| DPC (diskpool04) | **5155** | **3913** | DirectByteBuffer aligned to 4 KiB |

## Analysis

### NFS O_DIRECT is correctly working
- 140 MB/s single-thread write matches expectations for EC 6+2 with NFS overhead
- 556 MB/s read is reasonable for single-thread sequential O_DIRECT
- NFS requires 1 MiB buffer alignment (NFS server block size)
- Previous fio numbers (1496 write / 5071 read) were inflated by page cache / async engine

### DPC O_DIRECT shows extremely high throughput
- 4.6–5.2 GB/s write and 2.9–3.9 GB/s read
- DPC may be ignoring O_DIRECT flag internally (FUSE limitation)
- Or DPC's native protocol has genuinely lower overhead than NFS
- Need to verify with iostat/mountstats during sustained transfer

### Key Difference
DPC write is **33× faster** than NFS write (4623 vs 140 MB/s).  
DPC read is **5–7× faster** than NFS read (2889-3913 vs 556 MB/s).

## Methodology
```java
// O_DIRECT write
FileChannel.open(dst, CREATE, WRITE, TRUNCATE_EXISTING, ExtendedOpenOption.DIRECT)

// Aligned buffer for O_DIRECT compliance
ByteBuffer buf = ByteBuffer.allocateDirect(bs + alignment).alignedSlice(alignment);
```

## Files
- `/tmp/DirectTest.java` — NFS+DPC O_DIRECT test
- `/tmp/StorageBench.java` — buffered transfer benchmark  
- `/tmp/StorageBenchDPC.java` — DPC-adapted benchmark
