#!/usr/bin/env python3
"""Patch nfs4client.c to create extra transports after session setup."""
with open('nfs4client.c') as f:
    c = f.read()

# Find the end of nfs4_create_session function and add our hook
# Look for the pattern: "out:\n\treturn status;"
old = '\tout:\n\treturn status;\n}'
new = """\tout:
\treturn status;
}

/*
 * Create additional RPC transports for NFS multipath.
 * Called after session creation if remoteaddrs= was specified.
 */
static void dnfs_create_extra_transports(struct nfs_client *clp)
{
	struct nfs_multipath_addrs *list;
	struct rpc_clnt *clnt;
	int i;

	list = nfs_multipath_get_addrs();
	if (!list || list->count <= 1)
		goto out;

	clnt = clp->cl_rpcclient;
	if (!clnt)
		goto out;

	pr_info("NFS: nfs_multipath: creating %d extra transports\\n", list->count - 1);

	for (i = 1; i < list->count; i++) {
		struct sockaddr *sa = (struct sockaddr *)&list->addrs[i];
		size_t salen = sizeof(list->addrs[i]);
		int ret;

		ret = rpc_clnt_add_xprt(clnt, sa, salen, NULL, NULL);
		if (ret < 0)
			pr_warn("NFS: nfs_multipath: failed to add xprt %d: %d\\n", i, ret);
		else
			pr_info("NFS: nfs_multipath: added transport %d/%d\\n",
				i, list->count - 1);
	}

out:
	nfs_multipath_free_addrs(list);
}"""

if old in c:
    c = c.replace(old, new)
    with open('nfs4client.c', 'w') as f:
        f.write(c)
    print('nfs4client.c: added dnfs_create_extra_transports')
else:
    print('nfs4client.c: pattern not found')
