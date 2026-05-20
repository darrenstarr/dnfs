// SPDX-License-Identifier: GPL-2.0-only
#ifndef _NFS_MULTIPATH_H
#define _NFS_MULTIPATH_H

#define CONFIG_NFS_MULTIPATH_MAX_ADDRS 32

#include <linux/kernel.h>
#include <linux/socket.h>

struct nfs_multipath_addrs {
	unsigned int count;
	unsigned int max;
	struct sockaddr_storage addrs[];
};

int nfs_multipath_parse(void *unused, const char *value);
int nfs_multipath_parse_local(void *unused, const char *value);
struct nfs_multipath_addrs *nfs_multipath_get_addrs(void);
struct nfs_multipath_addrs *nfs_multipath_get_local_addrs(void);
void nfs_multipath_free_addrs(struct nfs_multipath_addrs *list);

#endif
