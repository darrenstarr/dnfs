# dnfs Ansible Playbook

Automates configuration of diskpool03 (Ubuntu 26.04) for NFSv4.1 multipath
to the Huawei OceanStor Pacific 9550 storage array.

## Layout

```
ansible/
├── ansible.cfg                   # Connection, inventory, pipelining
├── inventory/
│   └── production/
│       ├── hosts                 # diskpool03 with SSH jump chain
│       └── group_vars/
│           └── all.yml           # Storage IPs, mount options, kernel settings
├── playbooks/
│   └── deploy.yml               # Main playbook (network → kernel → mount → benchmark)
└── roles/
    ├── network/
    │   ├── tasks/main.yml
    │   └── library/ipv6_route.py     # /128 host routes to split traffic
    ├── kernel/
    │   ├── tasks/main.yml
    │   └── library/nfs_module_build.py  # NFS_MAX_CONNECTIONS bump + rebuild
    ├── nfs_mount/
    │   ├── tasks/main.yml
    │   └── library/nfs_multipath_mount.py  # 8 NFSv4.1 mounts
    └── benchmark/
        ├── tasks/main.yml
        └── library/nfs_benchmark.py    # fio single/aggregate read/write
```

## Usage

### Full deploy
```bash
cd ansible
ansible-playbook playbooks/deploy.yml
```

### Selective runs
```bash
# Just kernel module build
ansible-playbook playbooks/deploy.yml --tags kernel

# Network + mounts, skip benchmark
ansible-playbook playbooks/deploy.yml --skip-tags benchmark

# Benchmark only (assumes everything else is already set up)
ansible-playbook playbooks/deploy.yml --tags benchmark
```

### Performance-only
```bash
# Run only the benchmark, skip test file creation if it exists
ansible-playbook playbooks/deploy.yml --tags benchmark -e write_test_file=false
```

## What it does

1. **Network** — Adds /128 host routes to bind 4 storage IPs to each 100GbE NIC
   - `fc07:2::11,13,15,17` → `storagea.1001`
   - `fc07:2::12,14,16,18` → `storageb.1001`

2. **Kernel** — Patches NFS `fs_context.c` to bump `NFS_MAX_CONNECTIONS` to 32,
   builds nfs.ko against running kernel headers, installs and reloads.

3. **NFS mount** — Creates 8 mounts: `/dcache/pool1` through `/dcache/pool8`
   each to a different storage virtual port, `nconnect=16`, `rsize=wsize=1M`.

4. **Benchmark** — Creates a 20GB test file, runs:
   - Single-stream read (1 mount, 1 job, iodepth=64)
   - Single-stream write (1 mount, 1 job)
   - Aggregate read (8 mounts, single file, different offsets)
   - Aggregate write (8 mounts, 8 different files)

## Expected results

| Test | Minimum | Observed |
|------|---------|----------|
| Single-stream read | 30 Gb/s | 39.5 Gb/s |
| Aggregate read | 120 Gb/s | 180.3 Gb/s |
| Single-stream write | — | 21.4 Gb/s |
| Aggregate write | — | 144.3 Gb/s |

## Python modules

All roles use custom Python modules in `library/` rather than shell commands
or convoluted Ansible task chains. Each module is idempotent, has structured
JSON output, and reports `changed: true/false` correctly.

Module inventory:
- `ipv6_route.py` — add/remove/verify IPv6 host routes
- `nfs_module_build.py` — patch source, build, install, reload kernel module
- `nfs_multipath_mount.py` — mount/unmount NFS exports, count TCP connections
- `nfs_benchmark.py` — fio test runner with JSON output parsing
