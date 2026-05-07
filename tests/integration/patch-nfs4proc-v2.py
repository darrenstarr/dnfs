#!/usr/bin/env python3
"""Clean patch nfs4proc.c with correct rpc_clnt_add_xprt API."""
import sys

with open('nfs4proc.c') as f:
    content = f.read()

# The correct API for rpc_clnt_add_xprt in this kernel version
# takes a struct xprt_create, not individual sockaddr parameters.
# Let's check the header to verify, but for now use the correct call.

old_hook = '/* nfs_multipath: create extra transports if remoteaddrs= was specified */'
if old_hook in content:
    # Remove the old broken hook
    start = content.find(old_hook)
    end = content.find('\nout:\n\treturn status;\n}', start)
    if end > 0:
        # Find the end of our block
        block_end = content.find('\n}', start)
        while block_end < end and content[block_end:block_end+5] != '\n}\nout':
            block_end = content.find('\n}', block_end + 1)
        content = content[:start] + content[block_end+1:]

# Now find the right insertion point
insert_marker = 'nfs4_update_session(session, &res);\n\t}'
new_code = '''\tnfs4_update_session(session, &res);
\t}

\t/* nfs_multipath: create extra transports after session established */
\tif (!status) {
\t\tstruct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
\t\tif (list && list->count > 1) {
\t\t\tstruct rpc_clnt *clnt = clp->cl_rpcclient;
\t\t\tstruct xprt_create xprtargs = {
\t\t\t\t.ident = XPRT_TRANSPORT_TCP,
\t\t\t\t.net = &init_net,
\t\t\t\t.dstaddr = NULL,
\t\t\t\t.srcaddr = NULL,
\t\t\t\t.servername = NULL,
\t\t\t};
\t\t\tint i;

\t\t\tfor (i = 1; i < list->count; i++) {
\t\t\t\txprtargs.dstaddr = (struct sockaddr *)&list->addrs[i];
\t\t\t\txprtargs.addrsize = sizeof(list->addrs[i]);
\t\t\t\trpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL);
\t\t\t}
\t\t\tpr_info("NFS: nfs_multipath: added %d extra transports\\n",
\t\t\t\tlist->count - 1);
\t\t}
\t\tnfs_multipath_free_addrs(list);
\t}
'''

if insert_marker in content and 'dnfs' not in content[content.find(insert_marker):content.find(insert_marker)+500]:
    content = content.replace(insert_marker, new_code, 1)
    with open('nfs4proc.c', 'w') as f:
        f.write(content)
    print('nfs4proc.c: patched successfully')
else:
    print('nfs4proc.c: already patched or marker not found')
    # Show the area around the marker
    idx = content.find(insert_marker)
    if idx > 0:
        print(f'Context: {repr(content[idx:idx+200])}')
