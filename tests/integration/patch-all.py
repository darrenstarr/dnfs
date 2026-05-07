#!/usr/bin/env python3
"""Patch all NFS source files for dnfs support. Run from fs/nfs/."""
import re, sys

files = {}

# ====== 1. internal.h ======
with open('internal.h') as f:
    c = f.read()

# Add struct nfs_multipath_addrs (after NFS_SB_MASK line or similar)
if 'struct nfs_multipath_addrs' not in c:
    c = c.replace(
        'extern const struct export_operations nfs_export_ops;',
        'struct nfs_multipath_addrs {\n\tunsigned int count;\n\tunsigned int max;\n\tstruct sockaddr_storage addrs[];\n};\n\nextern const struct export_operations nfs_export_ops;'
    )
    print('internal.h: added dnfs_address_list struct')

# Add field to struct nfs_client
if 'cl_dnfs_remoteaddrs' not in c:
    c = c.replace(
        'unsigned int		cl_max_connect;',
        'unsigned int		cl_max_connect;\n\tstruct nfs_multipath_addrs *cl_dnfs_remoteaddrs;'
    )
    print('internal.h: added cl_dnfs_remoteaddrs')

with open('internal.h', 'w') as f:
    f.write(c)

# ====== 2. Kconfig ======
with open('Kconfig') as f:
    c = f.read()
if 'config DNFS' not in c:
    c = c.replace(
        'config NFS_V4_1',
        'config DNFS\n\tbool "NFS client multipath"\n\tdepends on NFS_V4_1\n\tdefault n\n\tselect SUNRPC\n\thelp\n\t  Client-side multipath for NFSv4.1.\n\t  Adds the remoteaddrs= mount option.\n\nconfig NFS_V4_1'
    )
    with open('Kconfig', 'w') as f:
        f.write(c)
    print('Kconfig: added CONFIG_NFS_MULTIPATH')

# ====== 3. Makefile ======
with open('Makefile') as f:
    c = f.read()
if 'nfs_multipath.o' not in c:
    c = c.replace(
        'nfs-y \t\t\t:= client.o dir.o file.o getroot.o inode.o super.o \\',
        'nfs-y \t\t\t:= client.o dir.o file.o getroot.o inode.o super.o \\\n\t\t\t   nfs_multipath.o \\'
    )
    with open('Makefile', 'w') as f:
        f.write(c)
    print('Makefile: added nfs_multipath.o')

# ====== 4. fs_context.c ======
with open('fs_context.c') as f:
    c = f.read()
if 'Opt_remoteaddrs' not in c:
    # Add to enum
    c = c.replace('\tOpt_rdma,', '\tOpt_rdma,\n\tOpt_remoteaddrs,\n\tOpt_localaddrs,', 1)
    # Add fsparam entries
    c = c.replace(
        'fsparam_flag  ("rdma",\t\tOpt_rdma),',
        'fsparam_flag  ("rdma",\t\tOpt_rdma),\n\tfsparam_string("remoteaddrs",\tOpt_remoteaddrs),\n\tfsparam_string("localaddrs",\tOpt_localaddrs),'
    )
    with open('fs_context.c', 'w') as f:
        f.write(c)
    print('fs_context.c: added mount options')

# ====== 5. super.c — add cleanup ======
with open('super.c') as f:
    c = f.read()
if 'dnfs_remoteaddrs' not in c:
    # Add dnf cleanup to nfs_free_server
    c = c.replace(
        'kfree(server->nfs_server_name);',
        'kfree(server->dnfs_remoteaddrs);\n\tkfree(server->nfs_server_name);'
    )
    with open('super.c', 'w') as f:
        f.write(c)
    print('super.c: added cleanup')

print('\nAll patches applied successfully.')
sys.exit(0)
