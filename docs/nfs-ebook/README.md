# NFS: The Definitive Guide — From Protocol to Kernel Implementation

> An in-depth reference covering the Network File System protocols, the Sun RPC layer, the Linux kernel NFS client implementation, and the path to multipath NFS.

## Table of Contents

| Chapter | Title | Topics |
|---------|-------|--------|
| 0 | [Preface](./ch00-preface.md) | Scope, conventions, kernel version reference |
| 1 | [NFS Protocol Evolution](./ch01-evolution.md) | v2 → v3 → v4 → v4.1 → v4.2, what each version brought |
| 2 | [Sun RPC Recap](./ch02-sunrpc.md) | RPC protocol, authentication, portmap/rpcbind, transport layers |
| 3 | [NFSv3 — How NFS Actually Works](./ch03-nfsv3.md) | Filehandles, operations, WRITE/COMMIT, NLM locking, the stateless model, what's wrong with v3 |
| 4 | [NFSv4 Architecture](./ch04-nfsv4.md) | COMPOUND RPC, operations, delegations, state model, recovery |
| 5 | [NFSv4.1: Sessions, pNFS, and Trunking](./ch05-nfs41.md) | Session model, parallel NFS layouts, multipath trunking, referrals |
| 6 | [Multipath NFS and Client-Side Trunking](./ch06-multipath.md) | How session trunking works, address lists, implementation patterns |
| 7 | [The Linux NFS Client Stack](./ch07-linux-client.md) | Architecture: VFS → NFS → RPC → xprt, module layering, key code paths |
| 8 | [The Linux RPC Layer (sunrpc.ko)](./ch08-sunrpc-impl.md) | rpc_clnt, rpc_task, xprt transport switch, multipath (xprtmultipath) |
| 9 | [dnfs: Distributed NFS Design](./ch09-dnfs-design.md) | Clean-room multipath, kernel patch architecture, code walk |
| A | [On-Wire Protocol Reference](./chaa-wire.md) | XDR primitives, COMPOUND encoding, operation tables |
| B | [Huawei eNFS Protocol Analysis](./chab-enfs-protocol.md) | EXTEND operation, shard routing, UUID filehandles, multipath architecture |
| C | [eNFS SunRPC Deviations](./chac-sunrpc-deviations.md) | All 29 changes to clnt.c, xprt.c, data structures, __GENKSYMS__ trick |

## Kernel Version

This book targets **Linux 7.0.0-14-generic** (Ubuntu 26.04 LTS / "Resolute"). Source trees and code references use the `linux-source-7.0.0` package.

## Related repositories

- [darrenstarr/dnfs](https://github.com/darrentarr/dnfs) — Kernel patch development
