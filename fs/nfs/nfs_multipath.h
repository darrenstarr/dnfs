/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _NFS_MULTIPATH_H
#define _NFS_MULTIPATH_H

#include <linux/types.h>
#include <linux/socket.h>

/* Maximum addresses per mount */
#define DNFS_MAX_ADDR_STRLEN 64
#define DNFS_MAX_OPTION_STRLEN 4096

#ifndef CONFIG_NFS_MULTIPATH_MAX_ADDRS
#define CONFIG_NFS_MULTIPATH_MAX_ADDRS 32
#endif

/* Parsed address list */
struct nfs_multipath_addrs {
	unsigned int               count;
	unsigned int               max;
	struct sockaddr_storage    addrs[];
};

/* API */
int nfs_multipath_parse(void *unused, const char *value);
struct nfs_multipath_addrs *nfs_multipath_get_addrs(void);
void nfs_multipath_free_addrs(struct nfs_multipath_addrs *list);

#endif /* _NFS_MULTIPATH_H */
