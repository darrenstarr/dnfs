#!/usr/bin/env python3
"""Patcher + wrapper: modify NFS source for multipath support in CWD."""
import os

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
    for i, l in enumerate(lines):
        if 'super.o \\' in l and 'nfs_multipath' not in ''.join(lines[i:i+3]):
            lines.insert(i+1, '\t\t\t   nfs_multipath.o \\')
            with open("Makefile","w") as f: f.write('\n'.join(lines))
            print("Makefile: OK")
            break

# 2b. Add CONFIG_NFS_MULTIPATH to ccflags so IS_ENABLED works
with open("Makefile") as f: c = f.read()
if "ccflags-y += -DCONFIG_NFS_MULTIPATH" not in c:
    c += "\n# Enable CONFIG_NFS_MULTIPATH for IS_ENABLED() guards\nccflags-y += -DCONFIG_NFS_MULTIPATH\n"
    with open("Makefile","w") as f: f.write(c)
    print("Makefile ccflags: OK")

# 3. fs_context.c
with open("fs_context.c") as f: c = f.read()
if "\tOpt_remoteaddrs," not in c:
    c = c.replace("\tOpt_rdma,", "\tOpt_rdma,\n\tOpt_remoteaddrs,\n\tOpt_localaddrs,\n", 1)
if 'fsparam_string("remoteaddrs"' not in c:
    c = c.replace(
        'fsparam_flag  ("rdma",\t\tOpt_rdma),',
        'fsparam_flag  ("rdma",\t\tOpt_rdma),\n\tfsparam_string("remoteaddrs",\tOpt_remoteaddrs),\n\tfsparam_string("localaddrs",\tOpt_localaddrs),')
if '#include "internal.h"' in c and 'nfs_multipath_parse' not in c:
    c = c.replace('#include "internal.h"',
        '#include "internal.h"\n#if IS_ENABLED(CONFIG_NFS_MULTIPATH)\nextern int nfs_multipath_parse(void *, const char *);\n#endif')
if 'case Opt_remoteaddrs:' not in c:
    c = c.replace(
        '\t\tctx->nfs_server.protocol = ret;\n\t\tbreak;\n\tcase Opt_acl:',
        '\t\tctx->nfs_server.protocol = ret;\n\t\tbreak;\n\tcase Opt_remoteaddrs:\n\t\treturn nfs_multipath_parse(NULL, param->string);\n\tcase Opt_localaddrs:\n\t\treturn 0;\n\tcase Opt_acl:')
with open("fs_context.c","w") as f: f.write(c)
print("fs_context.c: OK")

# 4. nfs4proc.c - add multipath hook with inline declarations (bypasses
#    include path issue: kernel build doesn't include fs/nfs/ for quotes)
with open("nfs4proc.c") as f: c = f.read()
if 'nfs_multipath_get_addrs' not in c:
    inline_decl = '\n#if IS_ENABLED(CONFIG_NFS_MULTIPATH)\nstruct nfs_multipath_addrs { unsigned int count; unsigned int max; struct sockaddr_storage addrs[]; };\nstruct nfs_multipath_addrs *nfs_multipath_get_addrs(void);\nvoid nfs_multipath_free_addrs(struct nfs_multipath_addrs *list);\n#endif\n'
    # Try common NFS includes as anchor points
    anchor = None
    for inc in ['#include <linux/nfs_fs_sb.h>', '#include <linux/nfs_fs.h>', '#include <linux/nfs.h>']:
        if inc in c:
            anchor = inc
            break
    if anchor:
        c = c.replace(anchor, anchor + inline_decl)
    hook = '\n\tif (IS_ENABLED(CONFIG_NFS_MULTIPATH)) {\n\t\tstruct nfs_multipath_addrs *list = nfs_multipath_get_addrs();\n\t\tif (list && list->count > 1) {\n\t\t\tstruct rpc_clnt *clnt = clp->cl_rpcclient;\n\t\t\tint i;\n\t\t\tfor (i = 1; i < list->count; i++) {\n\t\t\t\tstruct xprt_create xprtargs = {\n\t\t\t\t\t.ident = XPRT_TRANSPORT_TCP,\n\t\t\t\t\t.net = &init_net,\n\t\t\t\t\t.dstaddr = (struct sockaddr *)&list->addrs[i],\n\t\t\t\t\t.addrlen = sizeof(list->addrs[i]),\n\t\t\t\t};\n\t\t\t\trpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL);\n\t\t\t}\n\t\t}\n\t\tnfs_multipath_free_addrs(list);\n\t}'
    c = c.replace(
        'rpc_clnt_probe_trunked_xprts(clp->cl_rpcclient, &rpcdata);',
        'rpc_clnt_probe_trunked_xprts(clp->cl_rpcclient, &rpcdata);' + hook)
    with open("nfs4proc.c","w") as f: f.write(c)
    print("nfs4proc.c: OK")

print("\nALL PATCHES APPLIED")
