# Benchmark 05: Parallel Cross-Machine DPC Transfers

**Date:** 2026-06-22  
**Method:** 4-way parallel scp on storage VLAN 1002 (100GbE, MTU 9134)
**Test File:** 10 GB, `/dev/zero` on DPC mount

## Results

| Method | Time | Throughput | 
|--------|------|-----------|
| 1-stream scp (d2→d4) | 37.8s | 284 MB/s |
| 1-stream scp (d4→d2) | 19.5s | 549 MB/s |
| **4-stream scp (d2→d4)** | **5.8s** | **~1840 MB/s** |
| DPC local O_DIRECT write | — | 4623–5155 MB/s |
| DPC local O_DIRECT read | — | 2889–3913 MB/s |

## Analysis

- 4 parallel scp streams achieve 1.84 GB/s — ~6.5× speedup over single stream
- 1.84 GB/s = ~14.7 Gbps — still well below the 100GbE link capacity
- scp encryption overhead remains the bottleneck
- DPC local O_DIRECT shows the raw storage can do 3-5 GB/s
- Cross-machine throughput is network+software limited, not storage limited

## dCache Cluster Status

- Head node (diskpool01): Running stable with 4 NFS pools
- Pool nodes (diskpool02/04): Pools enabled, ZK connected
- **Satellite pools not registering with PoolManager** — PoolMonitor not discovering remote pools
- Next step: fix PoolMonitor/RemotePoolMonitor discovery or use standalone transfer tests

## Commands
```bash
# Parallel transfer
split -n 4 src.dat part_
for i in aa ab ac ad; do
  scp part_$i remote:part_$i &
done
wait
```
