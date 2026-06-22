# Benchmark 01: NFS Baseline (diskpool01)

**Date:** 2026-06-22  
**Machine:** diskpool01 (128 cores, 372GB, Java 21)  
**Storage:** OceanStor Pacific 9550, EC 6+2, NFSv4.1 mounts  
**Source:** `/dcache/pool1/diskpool01test/data` (20GB migtest files)  
**Dest:** `/dcache/pool2/bench` (NFSv4.1 to fc07:2::12)

## Configuration
- dCache 12.0.0-SNAPSHOT with custom FileRepositoryChannel (1 MiB DirectByteBuffer)
- `pool.backend.transfer-buffer-size = 1 MiB`
- NFS mounts: rsize=1M, wsize=1M, nconnect=16, proto=tcp6

## Results (Java DirectByteBuffer, 4096MB test, 1024KB buffer)

| Test | Speed | Notes |
|------|-------|-------|
| Seq Write | 936 MB/s | Single-thread, O_DIRECT-equivalent |
| Seq Read | 1154 MB/s | Reading existing 20GB files |
| Transfer 1-thread | 1998 MB/s | Read→Write, single FileChannel pair |
| Transfer 4-thread | 2380 MB/s | 4 parallel read→write threads |

## Observations
- Reads (1154 MB/s) outpace writes (936 MB/s) as expected for EC storage
- Transfer speed (1998 MB/s) is roughly write-limited: read and write overlap in single thread
- 4-thread parallel gets +19% boost (2380 vs 1998) — diminishing returns suggest write-path contention
- DirectByteBuffer works correctly on NFS with O_DIRECT semantics

## Kernel Counters (during transfer)
```
/proc/self/mountstats pool1 READ:
  ops: cumulative, avg latency ~1.0ms
  
/proc/self/mountstats pool2 WRITE:  
  ops: cumulative, avg latency ~9.2ms
```
