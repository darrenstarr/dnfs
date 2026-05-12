# dnfs — Distributed NFS

A clean-room implementation of a multipath NFS client for the upstream Linux kernel.

## Background

We operate a [Huawei OceanStor Pacific 9550](https://e.huawei.com/en/products/storage/oceanstor-pacific) cluster. Huawei's native DPC protocol delivers exceptional throughput but is closed-source, locked to outdated kernels with known security issues, and cannot be used in production-grade environments.

Huawei and other vendors (VAST, etc.) have been experimenting with alternatives to pNFS for their storage architectures. Huawei released **eNFS** as part of the OpenEuler kernel. We ported it to Ubuntu 26.04 / Linux 7.0 as a DKMS package (`enfs-dkms 0.1.6`) and achieved ~70 Gb/s line utilization. The target is ~140 Gb/s (2× 100 GbE with 802.3ad).

Rather than maintaining an out-of-tree DKMS package indefinitely, we are building a clean-room implementation designed from day one for upstream acceptance into the Linux kernel.

## Goals

- **Mainline-ready patch** — every change must be acceptable for submission to the upstream Linux kernel
- **Ubuntu package** — intermediate packaging for testing before upstream acceptance
- **Full documentation** — architecture docs, change documentation, LLM-assisted development annotations as required by kernel licensing rules
- **Clean-room design** — no derived code from the OpenEuler eNFS implementation

## Architecture (Stage 1)

The minimum viable parallelization target:

- **Client-side** multipath: specify multiple IPv4, IPv6, or hostname addresses for a single NFS mount
- Support from both CLI (`mount -o ...`) and `/etc/fstab`
- Runtime visibility of all transport endpoints via `/proc` / sysfs
- NFSv3 initially; NFSv4 on the roadmap

## Development

```bash
# Build NFS module against running kernel
cd ~/kernel-build/linux-source-7.0.0
echo '-14-generic' > localversion-ubuntu
cp /usr/src/linux-headers-$(uname -r)/Module.symvers .
make -j$(nproc) scripts prepare
make M=fs/nfs
sudo cp net/sunrpc/sunrpc.ko fs/nfs/{nfs,nfsv3,lockd}.ko \
        fs/nfs_common/{grace,nfs_acl}.ko \
        /lib/modules/$(uname -r)/updates/
sudo depmod -a && sudo modprobe nfs
```

See `AGENTS.md` for full development workflow and VM reset procedure.

## License

GPL-2.0-only — consistent with Linux kernel licensing. LLM-assisted contribution annotations follow kernel community conventions.

## Repo structure

```
linux-source-7.0.0/    — partial Ubuntu 7.0.0 kernel source (NFS/SunRPC only)
private/               — reference documentation, test machine configs (gitignored)
```

## Community

- **GitHub**: https://github.com/darrenstarr/dnfs
- **Gitter chat**: https://app.gitter.im/#/room/#dnfs:gitter.im

## Contributing

This project uses GitHub Issues for feature tracking and pull requests for all changes. The `main` branch is protected — all work flows through feature branches.

## Packaging

Build a `.deb` package for Ubuntu 26.04:

```bash
make deb
```

Installs the `dnfs-tools` package containing:

- `dnfs-stress` — NFS multipath stress test
- `dnfs-ansible` — Ansible playbooks for diskpool03 deployment
- Kernel module patches and build scripts
- Full documentation
