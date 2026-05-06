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

## Build VM

`ssh cave@10.200.1.186` (beast host, key auth). 16 vCPU, 188GB RAM, Ubuntu 26.04, kernel 7.0.0-14-generic.

Source extracted at `~/kernel-build/linux-source-7.0.0/`. Build recipe:

```bash
cd ~/kernel-build/linux-source-7.0.0
echo '-14-generic' > localversion-ubuntu
cp /usr/src/linux-headers-$(uname -r)/Module.symvers .
make -j$(nproc) scripts prepare
# edit source, then:
make M=fs/nfs
sudo cp net/sunrpc/sunrpc.ko fs/nfs/{nfs,nfsv3,lockd}.ko \
        fs/nfs_common/{grace,nfs_acl}.ko \
        /lib/modules/$(uname -r)/updates/
sudo depmod -a && sudo modprobe nfs
```

Base image stashed at `/opt/data/nfsdev/templates/resolute-base.qcow2`. To reset:
```bash
virsh destroy nfsdev && virsh undefine nfsdev
rm /opt/data/nfsdev/working.qcow2
qemu-img create -f qcow2 -b /opt/data/nfsdev/templates/resolute-base.qcow2 \
  -F qcow2 /opt/data/nfsdev/working.qcow2
virt-install --connect qemu:///system --name nfsdev --vcpus 16 --memory 196608 \
  --disk /opt/data/nfsdev/working.qcow2 --network bridge=br0,model=virtio \
  --graphics none --osinfo detect=on,name=linux2024 --import --noautoconsole
```

## GitHub workflow

- `main` branch is protected. All work flows through feature branches → PR → review → merge.
- Use issues for feature tracking. Reference issues in commits and PRs.
- The private/ directory (gitignored) contains reference docs and test machine info.
- Communication via private/ files: check for new files from `cave` at session start.

## Test machines (disconnected)

diskpool03 and diskpool04 are on a separate network behind a jump host and currently unreachable. Use the build VM for development.

