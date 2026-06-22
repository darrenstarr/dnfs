# dCache Performance Benchmark Cluster

## Architecture
```
diskpool01 (head + NFS pools) ─── ZK:2181, PnfsManager, PoolManager, WebDAV:2880
    │                            pools: diskpool01pool1-4 (NFS /dcache/pool1-4)
    │
diskpool02 (DPC pool) ─────────── satellite → diskpool01 ZK
    │                            pool: diskpool02pool1 (DPC /dcache/pool)
    │
diskpool03 (NFS pool) ─────────── satellite → diskpool01 ZK
    │                            pools: diskpool03pool5-8 (NFS /dcache/pool5-8)
    │
diskpool04 (DPC pool) ─────────── satellite → diskpool01 ZK
                                 pool: diskpool04pool1 (DPC /dcache/pool)
```

## Diskpool01 – Head Node Config
- Layout: `head-with-pool.conf`
- Runs: ZK, PnfsManager, PoolManager, WebDAV, FTP, GPlazma, 4 NFS pools
- ZK at localhost:2181
- DB: PostgreSQL at localhost

## Diskpool02 – DPC Pool Node
- Layout: `pool-dpc.conf`
- DPC mount at /dcache/pool → fc07:2:0:2::a:23
- Connects to diskpool01 ZK

## Diskpool03 – NFS Pool Node
- Layout: `pool-nfs.conf`
- NFS mounts at /dcache/pool5-8 → fc07:2::15-18
- Connects to diskpool01 ZK

## Diskpool04 – DPC Pool Node
- Layout: `pool-dpc.conf`
- DPC mount at /dcache/pool → fc07:2:0:2::a:25
- Connects to diskpool01 ZK
