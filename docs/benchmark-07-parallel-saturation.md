# Benchmark 07: Parallel Transfer Saturation — NFS vs DPC

**Date:** 2026-06-22  
**Method:** Java heap-buffer read/write loop, 256 MB per thread, 1 MiB buffer  
**Metrics:** Aggregate throughput scaling with thread count  

## NFS→NFS (diskpool01, fc07:2::11 → fc07:2::12)

| Threads | Throughput | Scaling |
|---------|-----------|---------|
| 1 | 453 MB/s | 1.00× |
| 2 | 901 MB/s | 1.99× |
| 4 | 1807 MB/s | 3.99× |
| 8 | 2308 MB/s | 5.09× |
| 16 | 2614 MB/s | 5.77× |
| **32** | **2724 MB/s** | **6.01× peak** |
| 64 | 2587 MB/s | 5.71× |

Saturation at 32 threads, ~2.7 GB/s ceiling = ~2560 effective IOPS (1 MiB blocks)

## DPC→DPC (diskpool02, DPC local I/O)

| Threads | Throughput | Scaling |
|---------|-----------|---------|
| 1 | 1115 MB/s | 1.00× |
| 2 | 2584 MB/s | 2.32× |
| 4 | 1254 MB/s | 1.12× |
| 8 | 2655 MB/s | 2.38× |
| 16 | 3038 MB/s | 2.72× |
| 32 | 4656 MB/s | 4.18× |
| **64** | **5356 MB/s** | **4.80× peak** |
| 128 | 5214 MB/s | 4.68× |

## DPC→DPC (diskpool04, DPC local I/O)

| Threads | Throughput | Scaling |
|---------|-----------|---------|
| 1 | 362 MB/s | 1.00× |
| 2 | 692 MB/s | 1.91× |
| 4 | 1377 MB/s | 3.80× |
| 8 | 2991 MB/s | 8.26× |
| 16 | 3064 MB/s | 8.46× |
| **32** | **5861 MB/s** | **16.2× peak** |
| 64 | 5762 MB/s | 15.9× |
| 128 | 5546 MB/s | 15.3× |

## Cross-Machine DPC→DPC (scp, storage VLAN)

| Streams | Time (1024 MB) | Effective BW |
|---------|---------------|-------------|
| 1 | 2.2s | 465 MB/s |
| 2 | 2.7s | 773 MB/s |
| 4 | 3.0s | 1373 MB/s |
| 8 | 3.0s | 2749 MB/s |
| 16 | 3.3s | 4899 MB/s |

SSH encryption limits per-stream throughput but parallel streams aggregate well.

## Transfer Buffer Size Impact (single thread, 1024 MB)

| Buffer | NFS→NFS | DPC→DPC | NFS vs 8KB | DPC vs 8KB |
|--------|---------|---------|-----------|-----------|
| 8 KB (JDK default) | 933 MB/s | 655 MB/s | 1.00× | 1.00× |
| 16 KB | 1256 MB/s | 941 MB/s | 1.35× | 1.44× |
| 64 KB | 1654 MB/s | 1547 MB/s | 1.77× | 2.36× |
| **1 MB (ours)** | **1810 MB/s** | **2521 MB/s** | **1.94×** | **3.85×** |

## Conclusion

- **Our 1 MiB transfer buffer provides 2-4× speedup** over JDK's default 8 KiB
- DPC's per-I/O overhead makes buffer size disproportionately impactful (3.85× vs 1.94×)
- NFS saturates at 2.7 GB/s, DPC at 5.4-5.9 GB/s
- DPC handles 2× more aggregate throughput than NFS at high parallelism
- Without our modification, DPC transfers would be capped at 655 MB/s single-thread
