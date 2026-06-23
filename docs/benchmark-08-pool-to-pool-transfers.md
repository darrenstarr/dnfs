# Benchmark 08: Pool-to-Pool Transfer Results

**Date:** 2026-06-23  
**Cluster:** 8 dCache pools across 8 OceanStor controllers (fc07:2::11-::18), 1 JVM  
**Buffer:** `pool.backend.transfer-buffer-size = 1 MiB` (our FileRepositoryChannel modification)

## Cross-Machine DPC→DPC (storage VLAN 1002, 100GbE, MTU 9134)

| Direction | Size | Time | Throughput |
|-----------|------|------|-----------|
| diskpool02 → diskpool04 | 10 GB | 29s | **353 MB/s** |
| diskpool04 → diskpool02 | 10 GB | 20s | **512 MB/s** |

SSH pipe (cat | ssh cat) — limited by single-thread SSH encryption.

## Local NFS→NFS (diskpool01, different controllers)

| Direction | Size | Time | Throughput |
|-----------|------|------|-----------|
| fc07:2::11 → fc07:2::12 | 20 GB | 27s | **~760 MB/s** |

dd single-threaded, Sequential read from controller 11, write to controller 12.

## dCache Transfer Buffer Size Impact (single-thread Java, 1024 MB)

| Buffer | NFS→NFS | DPC→DPC | NFS vs 8KB | DPC vs 8KB |
|--------|---------|---------|-----------|-----------|
| 8 KB (JDK default) | 933 MB/s | 655 MB/s | 1.00× | 1.00× |
| 16 KB | 1256 MB/s | 941 MB/s | 1.35× | 1.44× |
| 64 KB | 1654 MB/s | 1547 MB/s | 1.77× | 2.36× |
| **1 MB (ours)** | **1810 MB/s** | **2521 MB/s** | **1.94×** | **3.85×** |

## Parallel Saturation (Java heap buffers, local I/O)

| Platform | Peak Threads | Peak Throughput | 
|----------|-------------|----------------|
| NFS→NFS (diskpool01) | 32 | 2,724 MB/s |
| DPC→DPC (diskpool02) | 64 | 5,356 MB/s |
| DPC→DPC (diskpool04) | 32 | 5,861 MB/s |

## Cross-Machine Parallel (scp, storage VLAN)

| Streams | NFS→DPC 10GB | DPC→DPC 10GB |
|---------|-------------|-------------|
| 1 | 343 MB/s (30s) | 465 MB/s (22s) |
| 4 | — | 1,373 MB/s (7.5s) |
| 8 | — | 2,749 MB/s (3.7s) |
| 16 | — | 4,899 MB/s (2.1s) |

## Architecture

```
diskpool01 ─── 8 NFS pools to fc07:2::11─::18 (single JVM)
              │
              │ admin SSH port 22224
              │ ZK port 2181
              
diskpool02 ─── DPC mount (system:/dCache) on VLAN 1002
              │ pool enabled, cell tunnel to diskpool01
              
diskpool03 ─── NFS pool, cell tunnel to diskpool01

diskpool04 ─── DPC mount on VLAN 1002
              │ pool enabled, SSH keys exchanged with diskpool02
```

## Key Findings

1. **1 MiB buffer gives 1.9× (NFS) to 3.9× (DPC) speedup** over JDK's 8 KiB default
2. DPC benefits disproportionately — per-I/O FUSE overhead penalizes small transfers
3. NFS peaks at 2.7 GB/s (32 threads), DPC at 5.9 GB/s (64 threads)
4. DPC handles 2× more aggregate throughput at saturation
5. Cross-machine transfers via SSH are bottlenecked by encryption (~350-500 MB/s single stream)
6. Parallel streams on storage VLAN scale to ~4.9 GB/s with 16 scp streams
