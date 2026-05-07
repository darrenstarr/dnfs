/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _NFS_DNFS_H
#define _NFS_DNFS_H

#include <linux/types.h>
#include <linux/socket.h>

/* Maximum addresses per mount */
#define DNFS_MAX_ADDR_STRLEN 64
#define DNFS_MAX_OPTION_STRLEN 4096

#ifndef CONFIG_DNFS_MAX_REMOTE_ADDRS
#define CONFIG_DNFS_MAX_REMOTE_ADDRS 32
#endif

/* Parsed address list */
struct dnfs_address_list {
	unsigned int               count;
	unsigned int               max;
	struct sockaddr_storage    addrs[];
};

/* API */
int dnfs_parse_remoteaddrs(void *unused, const char *value);
struct dnfs_address_list *dnfs_get_address_list(void);
void dnfs_free_address_list(struct dnfs_address_list *list);

#endif /* _NFS_DNFS_H */
