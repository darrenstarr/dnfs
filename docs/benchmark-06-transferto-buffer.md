# Benchmark 06: FileRepositoryChannel.transferTo() Buffer Size Impact

**Date:** 2026-06-22  
**Method:** Java `DirectByteBuffer` read/write loop simulating dCache's modified `transferTo()`  
**Test:** 1024 MB transfer, page cache dropped, best of 3 iterations  
**Modification:** `pool.backend.transfer-buffer-size = 1 MiB` (vs JDK default 8 KiB)

## NFS→NFS (diskpool01, fc07:2::11 → fc07:2::12)

| Buffer | Speed | vs 8KB | 
|--------|-------|--------|
| 8 KB (JDK default) | 933 MB/s | baseline |
| 16 KB | 1256 MB/s | 1.35× |
| 64 KB | 1654 MB/s | 1.77× |
| **1 MB (ours)** | **1810 MB/s** | **1.94×** |

## DPC→DPC (diskpool02, DPC mount)

| Buffer | Speed | vs 8KB |
|--------|-------|--------|
| 8 KB (JDK default) | 655 MB/s | baseline |
| 16 KB | 941 MB/s | 1.44× |
| 64 KB | 1547 MB/s | 2.36× |
| **1 MB (ours)** | **2521 MB/s** | **3.85×** |

## Analysis

- **1 MB buffer provides 1.9–3.8× speedup** over JDK's default 8 KB
- DPC benefits more from large buffers than NFS (3.85× vs 1.94×)
- On NFS, diminishing returns above 64 KB (1654 → 1810 MB/s)
- On DPC, large buffers are critical — 8 KB is 4× slower
- Without our modification, DPC would run at 655 MB/s instead of 2521 MB/s

## dCache Code Path

Our modification replaces JDK's `FileChannel.transferTo()` (8 KB internal buffer) with a 1 MB DirectByteBuffer read/write loop in `FileRepositoryChannel.java`.

Files changed:
- `modules/dcache/src/main/java/org/dcache/pool/repository/FileRepositoryChannel.java`
- `modules/dcache/src/main/java/org/dcache/pool/repository/FlatFileStore.java`
- `modules/dcache/src/main/resources/org/dcache/pool/classic/pool.xml`
- `skel/share/defaults/pool.properties` — `pool.backend.transfer-buffer-size = 1 MiB`
