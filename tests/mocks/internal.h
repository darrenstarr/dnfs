/*
 * Mock for fs/nfs/internal.h — NFS client internal structures.
 */
#ifndef _MOCK_NFS_INTERNAL_H
#define _MOCK_NFS_INTERNAL_H

#include <sys/socket.h>
#include <netinet/in.h>
#include <stdbool.h>
#include <stddef.h>

#define DNFS_MAX_ADDR_STRLEN  64

#ifndef CONFIG_NFS_MULTIPATH_MAX_ADDRS
#define CONFIG_NFS_MULTIPATH_MAX_ADDRS 32
#endif

struct nfs_multipath_addrs; /* defined in nfs_multipath.h */

struct nfs_fs_context {
	struct {
		struct nfs_multipath_addrs *nfs_multipath_addrs;
		bool  dnfs_parsed;
		char *hostname;
		size_t hostnamelen;
		char *export_path;
		int   version;
	} nfs_server;
	int flags;
	void *private_data;
};

#endif /* _MOCK_NFS_INTERNAL_H */
