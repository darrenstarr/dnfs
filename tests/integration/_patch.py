#!/usr/bin/env python3
"""Patch NFS source files for dnfs support."""
import re, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Kconfig
with open('Kconfig') as f:
    c = f.read()
if 'CONFIG_NFS_MULTIPATH' not in c:
    c = c.replace(
        'config NFS_V4_1',
        'config DNFS\n\tbool "NFS client multipath"\n\tdepends on NFS_V4_1\n\tdefault n\n\thelp\n\t  Client-side multipath for NFSv4.1.\n\t  Adds remoteaddrs= mount option.\n\t  Zero server changes required.\n\t  If unsure, say N.\n\nconfig NFS_V4_1',
        1
    )
    with open('Kconfig', 'w') as f:
        f.write(c)
    print('Kconfig: done')

# Makefile
with open('Makefile') as f:
    lines = f.readlines()
new = []
added = False
for l in lines:
    new.append(l)
    if l.strip().endswith('super.o \\') and not added:
        new.append('\t\t\t   nfs_multipath.o \\\n')
        added = True
with open('Makefile', 'w') as f:
    f.writelines(new)
print(f'Makefile: done (added={added})')

# fs_context.c
with open('fs_context.c') as f:
    lines = f.readlines()
new = []
for l in lines:
    new.append(l)
    stripped = l.strip()
    if stripped == 'Opt_rdma,' and 'Opt_remoteaddrs' not in l:
        new[-1] = l  # already appended
        new.append('\tOpt_remoteaddrs,\n')
        new.append('\tOpt_localaddrs,\n')
for l in lines:
    stripped = l.strip()
    if 'fsparam_flag' in stripped and 'rdma' in stripped and 'remoteaddrs' not in l:
        # Add after this line
        pass
# Simpler: just add after rdma fsparam using string replace
with open('fs_context.c') as f:
    c = f.read()
if 'Opt_remoteaddrs' not in c:
    c = c.replace('\tOpt_rdma,', '\tOpt_rdma,\n\tOpt_remoteaddrs,\n\tOpt_localaddrs,', 1)
    c = c.replace(
        'fsparam_flag  ("rdma",\t\tOpt_rdma),',
        'fsparam_flag  ("rdma",\t\tOpt_rdma),\n\tfsparam_string("remoteaddrs",\tOpt_remoteaddrs),\n\tfsparam_string("localaddrs",\tOpt_localaddrs),',
    )
    with open('fs_context.c', 'w') as f:
        f.write(c)
    print('fs_context.c: done')
else:
    print('fs_context.c: already done')

# super.c
with open('super.c') as f:
    c = f.read()
if 'dnfs_remoteaddrs' not in c:
    c = c.replace(
        'kfree(server->server_name);',
        'kfree(server->dnfs_remoteaddrs);\n\tkfree(server->server_name);',
        1
    )
    with open('super.c', 'w') as f:
        f.write(c)
    print('super.c: done')

# nfs_multipath.c
src = 'nfs_multipath.c'
if os.path.exists(src):
    print(f'{src}: exists ({os.path.getsize(src)} bytes)')
else:
    print(f'{src}: NOT FOUND')

print('ALL PATCHES APPLIED')
