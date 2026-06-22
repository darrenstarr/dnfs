# Benchmark 04: Cross-Machine DPC Transfers

**Date:** 2026-06-22  
**Network:** Storage VLAN 1002, 100GbE, MTU 9134, IPv6  
**Method:** SSH key exchange on vlan1002, scp transfer

## SSH Key Setup
- Generated ed25519 keys on diskpool02 and diskpool04
- Exchanged `authorized_keys` via diskpoolmgmt
- Verified: both directions working on `fc07:2:0:2::a:23` ↔ `fc07:2:0:2::a:25`

## Local Write Speeds (dd, buffered)
| Machine | Speed | File |
|---------|-------|------|
| diskpool02 DPC | 175 MB/s | 10GB, dd if=/dev/zero |
| diskpool04 DPC | 273 MB/s | 10GB, dd if=/dev/zero |

## Cross-Machine Transfer (scp, 10GB file)

| Direction | Time | Speed | Notes |
|-----------|------|-------|-------|
| diskpool02 → diskpool04 | 37.8s | **284 MB/s** | scp encrypted |
| diskpool04 → diskpool02 | 19.5s | **549 MB/s** | scp encrypted |

## Analysis
- scp is single-thread TCP, limited by SSH encryption overhead
- Asymmetric: diskpool04 can push 549 MB/s but diskpool02 only 284 MB/s
- The bottleneck is likely scp/SSH, not the storage or network
- Equivalent to ~2.3-4.4 Gbps on the 100GbE link
- For comparison: NFS O_DIRECT write = 140 MB/s, DPC local direct = 4623 MB/s

## Next Steps
- Test with parallel transfers (multiple scp streams)  
- Test with raw netcat pipe to eliminate SSH overhead
- Get dCache pool-to-pool mover working for native transfer
- Profile kernel and network during transfers
