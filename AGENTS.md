# dnfs — Distributed NFS / enfs kernel patch workspace

## Repo structure

- `linux-source-7.0.0/` — partial Ubuntu 7.0.0 kernel source (NFS client + SunRPC + lockd + related headers only). NOT a full kernel tree.
- `private/enfs-documentation.md` — reference docs from the old enfs-dkms 0.1.6 package (mount syntax, patch series, OpenEuler vendor source).

## Kernel source layout (relevant directories)

- `fs/nfs/` — NFS client core (entrypoints: `client.c`, `super.c`, `fs_context.c`, `nfs3xdr.c`, `Makefile`)
- `fs/nfs_common/` — shared NFS code
- `net/sunrpc/` — SunRPC layer (entrypoints: `clnt.c`, `xprt.c`, `xprtmultipath.c`, `sched.c`, `Makefile`)
- `include/linux/nfs*` — NFS headers
- `include/linux/sunrpc/` — SunRPC headers
- `include/linux/lockd/` — NLM headers

## enfs patch series (23 patches)

The old enfs-dkms 0.1.6 modified these files (see `private/enfs-documentation.md`):
`fs/nfs/{Makefile,Kconfig,internal.h,super.c,fs_context.c,nfs3xdr.c,client.c}` +
`net/sunrpc/{Makefile,Kconfig,clnt.c,xprt.c,xprtmultipath.c,sunrpc_enfs_adapter.c}` +
`include/linux/sunrpc/{clnt.h,sched.h}` +
`include/linux/{nfs_fs_sb.h,nfs_xdr.h}`

## No local build/test infrastructure

This workspace has no Makefile, no tests, no linter, no CI config. Kernel builds happen on diskpool04 or a dedicated build VM. Any new AGENTS.md rules would need to be added here as the project evolves.
