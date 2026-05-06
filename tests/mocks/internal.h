/*
 * Mock for fs/nfs/internal.h — NFS client internal structures.
 *
 * This file must match the production internal.h structure layout
 * for the fields we use. For testing, we only define the subset
 * needed by the option parsing code.
 */
#ifndef _MOCK_NFS_INTERNAL_H
#define _MOCK_NFS_INTERNAL_H

#include <sys/socket.h>
#include <netinet/in.h>
#include <stdbool.h>
#include <stddef.h>

/* Maximum address string length (must match production). */
#define DNFS_MAX_ADDR_STRLEN  64

/* Config default — matches Kconfig default. */
#ifndef CONFIG_DNFS_MAX_REMOTE_ADDRS
#define CONFIG_DNFS_MAX_REMOTE_ADDRS 32
#endif

/**
 * struct dnfs_address_list — Parsed list of server addresses.
 * @count:  Number of valid addresses.
 * @max:    Maximum capacity of the addrs array.
 * @addrs:  Variable-length array of parsed addresses.
 */
struct dnfs_address_list {
	unsigned int               count;
	unsigned int               max;
	struct sockaddr_storage    addrs[];
};

/**
 * struct nfs_fs_context — Minimal mock of NFS mount context.
 *
 * Only defines the fields needed by the option parser.
 * The production structure is much larger but the mock
 * only needs the dnfs fields.
 */
struct nfs_fs_context {
	struct {
		struct dnfs_address_list *dnfs_remoteaddrs;
		bool                     dnfs_parsed;
		char                     *hostname;
		size_t                   hostnamelen;
		char                     *export_path;
		int                      version;
	} nfs_server;
	int flags;
	void *private_data;
};

/* Function prototypes from dnfs_parse.c */
extern int  dnfs_parse_remoteaddrs(struct nfs_fs_context *ctx, const char *value);
extern void dnfs_free_address_list(struct dnfs_address_list *list);

#endif /* _MOCK_NFS_INTERNAL_H */
