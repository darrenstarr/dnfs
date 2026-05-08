#!/usr/bin/env python3
"""Patch NFS kernel source for multipath support on diskpool03."""
import os, re, sys

os.chdir(os.path.expanduser("~/kernel-build/linux-source-7.0.0/fs/nfs"))

def patch_file(fn, old, new):
    with open(fn) as f: c = f.read()
    if old in c:
        c = c.replace(old, new)
        with open(fn,'w') as f: f.write(c)
        return True
    return False

# 1. Kconfig
with open("Kconfig") as f: c = f.read()
if "CONFIG_NFS_MULTIPATH" not in c:
    c = c.replace("config NFS_V4_1_IMPLEMENTATION_ID_DOMAIN",
        "config NFS_MULTIPATH\n\tbool \"NFS client multipath\"\n\tdepends on NFS_FS\n\tdefault n\n\thelp\n\t  Client-side multipath via remoteaddrs= mount option.\n\nconfig NFS_V4_1_IMPLEMENTATION_ID_DOMAIN")
    with open("Kconfig","w") as f: f.write(c)
    print("Kconfig: OK")

# 2. Makefile  
with open("Makefile") as f: c = f.read()
if "nfs_multipath.o" not in c:
    lines = c.split('\n')
    found = False
    for i, l in enumerate(lines):
        if 'super.o \\' in l and 'nfs_multipath' not in ''.join(lines[i:i+3]):
            lines.insert(i+1, '\t\t\t   nfs_multipath.o \\')
            found = True
            break
    if found:
        with open("Makefile","w") as f: f.write('\n'.join(lines))
        print("Makefile: OK")

# 3. fs_context.c
with open("fs_context.c") as f: c = f.read()

# Add enum entry
if "\tOpt_remoteaddrs," not in c:
    c = c.replace("\tOpt_rdma,", "\tOpt_rdma,\n\tOpt_remoteaddrs,\n\tOpt_localaddrs,\n", 1)

# Add fsparam entries
if 'fsparam_string("remoteaddrs"' not in c:
    c = c.replace(
        'fsparam_flag  ("rdma",\t\tOpt_rdma),',
        'fsparam_flag  ("rdma",\t\tOpt_rdma),\n\tfsparam_string("remoteaddrs",\tOpt_remoteaddrs),\n\tfsparam_string("localaddrs",\tOpt_localaddrs),')

# Add extern declaration after internal.h include
if '#include "internal.h"' in c and 'nfs_multipath_parse' not in c:
    c = c.replace('#include "internal.h"',
        '#include "internal.h"\n#if IS_ENABLED(CONFIG_NFS_MULTIPATH)\nextern int nfs_multipath_parse(void *, const char *);\n#endif')

# Add case handlers (after Opt_rdma break, before Opt_acl)
if 'case Opt_remoteaddrs:' not in c:
    c = c.replace(
        '\t\tctx->nfs_server.protocol = ret;\n\t\tbreak;\n\tcase Opt_acl:',
        '\t\tctx->nfs_server.protocol = ret;\n\t\tbreak;\n\tcase Opt_remoteaddrs:\n\t\treturn nfs_multipath_parse(NULL, param->string);\n\tcase Opt_localaddrs:\n\t\treturn 0;\n\tcase Opt_acl:')

with open("fs_context.c","w") as f: f.write(c)
print("fs_context.c: OK")

# 4. nfs4proc.c - add transport creation hook
with open("nfs4proc.c") as f: c = f.read()

if 'nfs_multipath_get_addrs' not in c:
    # Add include
    if '#include <linux/nfs_fs_sb.h>' in c:
        c = c.replace('#include <linux/nfs_fs_sb.h>',
            '#include <linux/nfs_fs_sb.h>\n#if IS_ENABLED(CONFIG_NFS_MULTIPATH)\n#include "nfs_multipath.h"\n#endif')
    
    # Add hook before out: label in nfs4_proc_create_session
    hook = '\n\tif (IS_ENABLED(CONFIG_NFS_MULTIPATH)) {\n\t\tstruct nfs_multipath_addrs *list = nfs_multipath_get_addrs();\n\t\tif (list && list->count > 1) {\n\t\t\tstruct rpc_clnt *clnt = clp->cl_rpcclient;\n\t\t\tint i;\n\t\t\tfor (i = 1; i < list->count; i++) {\n\t\t\t\tstruct xprt_create xprtargs = {\n\t\t\t\t\t.ident = XPRT_TRANSPORT_TCP,\n\t\t\t\t\t.net = &init_net,\n\t\t\t\t\t.dstaddr = (struct sockaddr *)&list->addrs[i],\n\t\t\t\t\t.addrlen = sizeof(list->addrs[i]),\n\t\t\t\t};\n\t\t\t\trpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL);\n\t\t\t}\n\t\t}\n\t\tnfs_multipath_free_addrs(list);\n\t}'
    
    c = c.replace(
        'rpc_clnt_probe_trunked_xprts(clp->cl_rpcclient, &rpcdata);',
        'rpc_clnt_probe_trunked_xprts(clp->cl_rpcclient, &rpcdata);' + hook)
    
    with open("nfs4proc.c","w") as f: f.write(c)
    print("nfs4proc.c: OK")

print("\nALL PATCHES APPLIED")
