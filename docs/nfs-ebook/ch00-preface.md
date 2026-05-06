# Chapter 0: Preface

## Scope

This book covers the Network File System (NFS) protocols through the lens of the Linux kernel implementation, with a focus on NFSv4 and NFSv4.1. It is intended for:

- **Kernel developers** working on NFS client or server code
- **Systems engineers** deploying NFS at scale who want to understand the protocol mechanics
- **Storage architects** evaluating multipath and parallel filesystem access patterns

## NFSv3 Is Legacy

Versions 2 and 3 of the NFS protocol are treated as **historical reference only**. They lack:

- A native state model (delegations, locks, opens managed by the server)
- Session-based recovery (client ID + lease → session ID + slot table)
- Multipath trunking (NFSv4.1)
- Parallel data access (pNFS, NFSv4.1)
- Security negotiation (RPCSEC_GSS)

Where NFSv3 behavior illuminates a design decision in v4/v4.1, it is mentioned. Otherwise, this book focuses entirely on NFSv4 and its minor versions.

## Sun RPC Is Prerequisite Knowledge

We assume the reader is familiar with:

- The RPC message format (call header, reply header, credentials, verifiers)
- Portmapper / rpcbind
- Auth flavours (AUTH_SYS, AUTH_NONE, RPCSEC_GSS)
- XDR encoding

Chapter 2 provides a brief recap for reference, but it is not a tutorial.

## Kernel Reference

All code paths and data structures reference the **Linux 7.0.0** kernel source (Ubuntu 26.04 LTS, Resolute), specifically the source tarball from `linux-source-7.0.0`.

Key source directories:

| Directory | Contents |
|-----------|----------|
| `fs/nfs/` | NFS client (v2, v3, v4, v4.1, v4.2) |
| `fs/nfs_common/` | Shared NFS helpers (nfsacl, grace) |
| `net/sunrpc/` | Sun RPC layer (clnt, xprt, sched, auth) |
| `include/linux/nfs*` | NFS protocol headers |
| `include/linux/sunrpc/` | RPC layer headers |

## Diagrams

All diagrams in this book use Mermaid syntax and render natively in GitHub-flavoured Markdown.
