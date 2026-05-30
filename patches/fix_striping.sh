#!/bin/bash
NFSDIR=/home/netadmin/kernel-build/linux-source-7.0.0/fs/nfs
set -e

# Fix internal.h - insert after max_connect
python3 -c "
p = '$NFSDIR/internal.h'
c = open(p).read()
add = '''
#if IS_ENABLED(CONFIG_NFS_MULTIPATH)
\tunsigned int\t\tmpath_num_xprts;
\tstruct rpc_xprt\t\t**mpath_xprts;
#endif
'''
if 'mpath_num_xprts' not in c:
    c = c.replace('unsigned int nconnect;\n\tunsigned int max_connect;\n\tstruct net *net;',
                  'unsigned int nconnect;\n\tunsigned int max_connect;\n' + add + '\n\tstruct net *net;')
    open(p,'w').write(c)
    print('internal.h fixed')
else:
    print('already patched')
"

# Fix pagelist.c - add sunrpc/clnt.h include
python3 -c "
p = '$NFSDIR/pagelist.c'
c = open(p).read()
if 'sunrpc/clnt.h' not in c:
    c = c.replace('#include <linux/sunrpc/bc_xprt.h>',
                  '#include <linux/sunrpc/bc_xprt.h>\n#include <linux/sunrpc/clnt.h>')
    open(p,'w').write(c)
    print('include added')
"

# Fix nfs3client.c - store transports (the list_for_each_entry needs xprt_switch.h)
python3 -c "
p = '$NFSDIR/nfs3client.c'
c = open(p).read()
if 'mpath_xprts' not in c:
    # Add the store code BEFORE the 'pr_info' line
    store = '''\n#if IS_ENABLED(CONFIG_NFS_MULTIPATH)\n\tif (count > 0 && !server->mpath_xprts) {\n\t\tstruct rpc_xprt_switch *xps;\n\t\tstruct rpc_xprt *pos;\n\t\tint idx = 0;\n\t\tserver->mpath_xprts = kcalloc(count, sizeof(struct rpc_xprt *), GFP_KERNEL);\n\t\tif (server->mpath_xprts) {\n\t\t\txps = clnt->cl_xpi.xpi_xpswitch;\n\t\t\tlist_for_each_entry(pos, &xps->xps_xprt_list, xprt_switch) {\n\t\t\t\tif (idx < count) server->mpath_xprts[idx++] = pos;\n\t\t\t}\n\t\t\tserver->mpath_num_xprts = idx;\n\t\t\tpr_info(\"NFSv3 striping: stored %d transports\\n\", idx);\n\t\t}\n\t}\n#endif'''
    c = c.replace('if (count > 0)\n\t\t\tpr_info(\"NFSv3 multipath: added %d transports\\\\n\", count);',
                  'if (count > 0) {\n\t\t\tpr_info(\"NFSv3 multipath: added %d transports\\\\n\", count);' + store + '\n\t\t}')
    open(p,'w').write(c)
    print('nfs3client.c fixed')
"

# Rebuild
cd /home/netadmin/kernel-build/linux-source-7.0.0
make -j$(nproc) -C /lib/modules/7.0.0-15-generic/build M=$NFSDIR modules 2>&1 | tail -5
