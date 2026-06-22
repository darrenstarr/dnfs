# Benchmark 03: Cluster Setup & Transfer Architecture

**Date:** 2026-06-22

## Cluster Architecture

```
diskpool01 (head + NFS pools)     diskpool02 (DPC pool)      diskpool04 (DPC pool)
├── ZK: embedded in JVM            ├── ZK client → diskpool01  ├── ZK client → diskpool01
├── PnfsManager                   ├── pool: diskpool02pool1   ├── pool: diskpool04pool1
├── PoolManager                   ├── path: /dcache/pool      ├── path: /dcache/pool
├── 4 NFS pools (1-4)             └── meta: file              └── meta: file
└── NFS mounts to fc07:2::11-14       DPC to vlan1002            DPC to vlan1002
```

## Issues Encountered

1. **Head DNS resolution**: Satellite pools use ZK topology to discover head address as `tcp://diskpool01:11111`. `diskpool01` hostname must resolve from pool nodes.

2. **DNS resolution**: Fixed by adding `109.105.125.104 diskpool01` to `/etc/hosts` on pool nodes.

3. **Berkeley DB lock**: DPC FUSE mount doesn't support BDB lock files properly. Switched pool metadata to `file` mode (`pool.meta = file`).

4. **SSH host keys**: Pool nodes need SSH host keys generated (`/etc/dcache/admin/ssh_host_rsa_key`).

5. **Cross-machine SSH**: Storage VLAN (vlan1002) lacks passwordless SSH between pool nodes. Blocked scp/rsync transfers.

## dCache Configuration

### Head (diskpool01)
```
dcache.layout = minimal-head
dcache.domains = dCacheDomain
dcache.zookeeper.connection = localhost:2181
dcache.broker.scheme = core
pool.backend.transfer-buffer-size = 1 MiB
```

### Pool nodes (diskpool02/04)
```
dcache.layout = pool-layout
dcache.zookeeper.connection = 109.105.125.104:2181
dcache.broker.scheme = satellite
pool.backend.transfer-buffer-size = 1 MiB
```

## Transfer Benchmarks (Raw I/O, No dCache Mover)

| Path | Write | Read | Notes |
|------|-------|------|-------|
| NFS → NFS (diskpool01) | 140 MB/s | 556 MB/s | O_DIRECT, 1MiB aligned |
| DPC → DPC (diskpool02) | 4623 MB/s | 2889 MB/s | O_DIRECT, 4KiB aligned |
| DPC → DPC (diskpool04) | 5155 MB/s | 3913 MB/s | O_DIRECT, 4KiB aligned |
| DPC dd buffered | ~3000 MB/s | — | Non-direct, page cached |
| DPC dd direct | ~1400 MB/s | — | `dd oflag=direct` |
| NFS fio async | 1496 MB/s | 5071 MB/s | libaio, iodepth=16, page cache effects |

## Key Observations

1. **DPC massively outperforms NFS for raw I/O** — 33× faster writes, 5-7× faster reads
2. **O_DIRECT semantics differ**: NFS enforces strict alignment (1 MiB block), DPC/FUSE may silently ignore O_DIRECT
3. **dCache pool-to-pool transfers not yet tested** — cluster running but satellites not registering with PoolManager
4. **Cross-machine benchmarks blocked** on SSH key setup for storage VLAN
