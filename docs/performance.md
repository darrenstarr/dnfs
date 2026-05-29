# NFS Multipath Performance Results

## Environment
- **Machines**: diskpool01 (128 cores, 372GB RAM, dual 100GbE)
- **Storage**: Huawei OceanStor Pacific 9550, 8 virtual ports, 4.3PB
- **Kernel**: 7.0.0-15-generic with custom dnfs NFS module
- **Custom module srcversion**: E413CDA689DCEB26ECB853A
- **NFS**: 4.1, rsize=wsize=1M, nconnect=16, MTU 9134

## Single Mount Performance

### Pure NFS Read (dd, 1MB blocks)
- Cold cache: 956 MB/s (7.6 Gb/s)

### Java Read+Write (1MB buffer, AsynchronousFileChannel)

| Concurrent Reads | Without nconnect | With nconnect=16 |
|-----------------|-----------------|------------------|
| 1               | 682 MB/s        | 949 MB/s         |
| 2               | 3,526 MB/s      | 5,518 MB/s       |
| 4               | 10,781 MB/s     | 9,670 MB/s       |
| 8               | 10,722 MB/s     | 11,278 MB/s      |
| 16              | 10,657 MB/s     | 11,393 MB/s      |

With nconnect=16 and 16 concurrent reads, a single NFS mount achieves 11.4 GB/s (91 Gb/s),
nearly saturating the 100GbE link.

## Per-Chunk Timing (1MB buffer, single-threaded)
- Average NFS read: 1099 μs
- Average page cache write: 107 μs
- Ratio: 10:1 (reads dominate transfer time)

## 8-Mount Multipath
- Aggregate read (single file, 8 offsets): 15.1 GiB/s (130 Gb/s)

## nconnect Caveats
- `nconnect=16` must be set at mount time on a FRESH mount
- Reusing an old `nfs_server` struct (same server IP) ignores new mount options
- Must unmount ALL filesystems to a server IP before remounting with nconnect
- Verified: 17 TCP connections to `fc07:2::18` with nconnect=16
- `/proc/mounts` shows `nconnect=16` when properly applied

## Build Recipes
See `ansible/dnfs_build.py` for one-shot build script.
See `ansible/roles/kernel/tasks/main.yml` for Ansible-based build.

## Cross-Machine Transfer

### Raw Network (iperf3, storage VLAN)
| Direction | Single stream | 4 streams |
|-----------|--------------|-----------|
| diskpool01 → diskpool03 | 37 Gb/s | 89 Gb/s |
| diskpool03 → diskpool01 | 20 Gb/s | 78 Gb/s |

### Single-stream NFS-backed transfer (NFSv4.1 + async pipeline + TCP)
- 20GB file: 1164 MB/s (9.8 Gb/s)
- Bottleneck: single TCP connection serializes reads and writes

### Source-based policy routing
```bash
# /etc/iproute2/rt_tables
100 storagea
200 storageb

# Per-table routes
ip -6 route add fc07:2::/64 dev storagea.1001 table 100
ip -6 route add fc07:2::/64 dev storageb.1001 table 200

# Policy rules
ip -6 rule add from fc07:2::1:a:22 table 100 pref 100
ip -6 rule add from fc07:2::2:a:22 table 200 pref 100
```
