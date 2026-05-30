#!/usr/bin/env python3
"""Apply NFS I/O striping patch to kernel source tree."""

import sys, os

NFSDIR = sys.argv[1] if len(sys.argv) > 1 else "/home/netadmin/kernel-build/linux-source-7.0.0/fs/nfs"

# 1. Patch internal.h: add multipath transport storage to nfs_server
print("=== Patching internal.h ===")
with open(f"{NFSDIR}/internal.h") as f:
    c = f.read()

# Add after nconnect field
add = """
#if IS_ENABLED(CONFIG_NFS_MULTIPATH)
	unsigned int		mpath_num_xprts;
	struct rpc_xprt		**mpath_xprts;
#endif
"""
if "mpath_num_xprts" not in c:
    c = c.replace("\tunsigned int\t\tnconnect;\n", "\tunsigned int\t\tnconnect;\n" + add)
    with open(f"{NFSDIR}/internal.h", "w") as f:
        f.write(c)
    print("  internal.h: added multipath transport storage")
else:
    print("  internal.h: already patched")

# 2. Patch nfs3client.c: store transports in server after creation
print("=== Patching nfs3client.c ===")
with open(f"{NFSDIR}/nfs3client.c") as f:
    c = f.read()

store_code = """
#if IS_ENABLED(CONFIG_NFS_MULTIPATH)
	if (count > 0) {
		int i, idx = 0;
		server->mpath_xprts = kcalloc(count, sizeof(struct rpc_xprt *), GFP_KERNEL);
		if (server->mpath_xprts) {
			/* Collect xprts from the xprt_switch */
			struct rpc_xprt_switch *xps = clnt->cl_xpi.xpi_xpswitch;
			struct rpc_xprt *pos;
			list_for_each_entry(pos, &xps->xps_xprt_list, xprt_switch) {
				if (idx < count)
					server->mpath_xprts[idx++] = pos;
			}
			server->mpath_num_xprts = idx;
			pr_info("NFSv3 striping: stored %d transports for server\n", idx);
		}
	}
#endif
"""

if "mpath_xprts" not in c:
    c = c.replace(
        "if (count > 0)\n\t\tpr_info(\"NFSv3 multipath: added %d transports\\n\", count);",
        "if (count > 0) {\n\t\tpr_info(\"NFSv3 multipath: added %d transports\\n\", count);" + store_code + "\n\t}"
    )
    with open(f"{NFSDIR}/nfs3client.c", "w") as f:
        f.write(c)
    print("  nfs3client.c: added transport storage")
else:
    print("  nfs3client.c: already patched")

# 3. Patch pagelist.c: stripe reads across transports
print("=== Patching pagelist.c ===")
with open(f"{NFSDIR}/pagelist.c") as f:
    c = f.read()

if "mpath_stripe" not in c:
    # Add function before nfs_pageio_setup_mirroring
    stripe_func = """
#if IS_ENABLED(CONFIG_NFS_MULTIPATH)
/*
 * Check if the server has multipath transports and set up mirroring
 * to distribute I/O across all available transports.
 */
static unsigned int nfs_mpath_get_mirror_count(struct nfs_server *server)
{
	if (server->mpath_num_xprts > 1)
		return server->mpath_num_xprts;
	return 1;
}
#endif
"""
    c = c.replace(
        "static void nfs_pageio_setup_mirroring(struct nfs_pageio_descriptor *pgio,",
        stripe_func + "\nstatic void nfs_pageio_setup_mirroring(struct nfs_pageio_descriptor *pgio,"
    )
    
    # Modify nfs_pageio_setup_mirroring to check multipath
    old_mirror = "mirror_count = pgio->pg_ops->pg_get_mirror_count(pgio, req);"
    new_mirror = """	mirror_count = pgio->pg_ops->pg_get_mirror_count(pgio, req);
#if IS_ENABLED(CONFIG_NFS_MULTIPATH)
	{
		unsigned int mc = nfs_mpath_get_mirror_count(NFS_SERVER(pgio->pg_inode));
		if (mc > 1)
			mirror_count = mc;
	}
#endif"""
    c = c.replace(old_mirror, new_mirror)
    
    with open(f"{NFSDIR}/pagelist.c", "w") as f:
        f.write(c)
    print("  pagelist.c: added striping support")
else:
    print("  pagelist.c: already patched")

# 4. Patch pagelist.c: nfs_generic_pg_pgios to pin transport for multipath mirrors
print("=== Adding transport pinning in pagelist.c ===")
with open(f"{NFSDIR}/pagelist.c") as f:
    c = f.read()

if "mpath_pin_xprt" not in c:
    old_initiate = "ret = nfs_initiate_pgio(NFS_CLIENT(hdr->inode),"
    new_initiate = """		ret = nfs_initiate_pgio(NFS_CLIENT(hdr->inode),
					hdr,
					hdr->cred,
					NFS_PROTO(hdr->inode),
					desc->pg_rpc_callops,
					desc->pg_ioflags,
					RPC_TASK_CRED_NOREF | task_flags,
					localio);
#if IS_ENABLED(CONFIG_NFS_MULTIPATH)
		if (ret == 0 && hdr->task) {
			struct nfs_server *server = NFS_SERVER(hdr->inode);
			if (server->mpath_num_xprts > 1) {
				int xprt_idx = hdr->pgio_mirror_idx % server->mpath_num_xprts;
				if (server->mpath_xprts[xprt_idx])
					rpc_task_set_xprt(hdr->task, server->mpath_xprts[xprt_idx]);
			}
		}
#endif
	}
	return ret;"""

    # Find and replace the section
    c = c.replace(
        "ret = nfs_initiate_pgio(NFS_CLIENT(hdr->inode),\n\t\t\t\t\thdr,\n\t\t\t\t\thdr->cred,\n\t\t\t\t\tNFS_PROTO(hdr->inode),\n\t\t\t\t\tdesc->pg_rpc_callops,\n\t\t\t\t\tdesc->pg_ioflags,\n\t\t\t\t\tRPC_TASK_CRED_NOREF | task_flags,\n\t\t\t\t\tlocalio);\n\t}\n\treturn ret;",
        new_initiate
    )
    with open(f"{NFSDIR}/pagelist.c", "w") as f:
        f.write(c)
    print("  pagelist.c: added transport pinning")
else:
    print("  pagelist.c: transport pinning already present")

print("\nALL STRIPING PATCHES APPLIED")
