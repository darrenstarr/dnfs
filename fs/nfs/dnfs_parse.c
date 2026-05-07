// SPDX-License-Identifier: GPL-2.0-only
/*
 * fs/nfs/dnfs_parse.c -- Distributed NFS mount option parsing
 */
#include <linux/kernel.h>
#include <linux/string.h>
#include <linux/slab.h>
#include <linux/errno.h>
#include <linux/sunrpc/addr.h>
#include <linux/mutex.h>
#include "dnfs.h"

#ifndef CONFIG_DNFS_MAX_REMOTE_ADDRS
#define CONFIG_DNFS_MAX_REMOTE_ADDRS 32
#endif
#define DNFS_MAX_OPTION_STRLEN 4096

static struct dnfs_address_list *g_dnfs_list;
static DEFINE_MUTEX(g_dnfs_lock);

int __maybe_unused dnfs_parse_remoteaddrs(void *unused, const char *value)
{
	struct dnfs_address_list *list;
	const char *p, *next;
	unsigned int count = 0;
	size_t val_len, token_len;
	(void)unused;

	if (!value || !*value) return -EINVAL;
	val_len = strlen(value);
	if (val_len > DNFS_MAX_OPTION_STRLEN) return -E2BIG;

	p = value;
	while (*p) {
		while (*p == '~') p++;
		if (!*p) break;
		count++;
		if (count >= CONFIG_DNFS_MAX_REMOTE_ADDRS) break;
		p = strchr(p, '~');
		if (!p) break;
		p++;
	}
	if (count == 0) return -EINVAL;
	if (count > CONFIG_DNFS_MAX_REMOTE_ADDRS) return -E2BIG;

	list = kzalloc(sizeof(*list) + count * sizeof(list->addrs[0]), GFP_KERNEL);
	if (!list) return -ENOMEM;
	list->count = 0;
	list->max = count;

	p = value;
	while (*p && list->count < count) {
		while (*p == '~') p++;
		if (!*p) break;
		next = strchr(p, '~');
		token_len = next ? (size_t)(next - p) : strlen(p);

		if (!rpc_pton(&init_net, p, token_len,
			(struct sockaddr *)&list->addrs[list->count],
			sizeof(list->addrs[list->count]))) {
			pr_warn("NFS: dnfs: invalid address\n");
			kfree(list);
			return -EINVAL;
		}
		list->count++;
		p = next ? next + 1 : NULL;
	}

	mutex_lock(&g_dnfs_lock);
	kfree(g_dnfs_list);
	g_dnfs_list = list;
	mutex_unlock(&g_dnfs_lock);
	return 0;
}

struct dnfs_address_list *__maybe_unused dnfs_get_address_list(void)
{
	struct dnfs_address_list *list;
	mutex_lock(&g_dnfs_lock);
	list = g_dnfs_list;
	g_dnfs_list = NULL;
	mutex_unlock(&g_dnfs_lock);
	return list;
}

void __maybe_unused dnfs_free_address_list(struct dnfs_address_list *list)
{
	kfree(list);
}

EXPORT_SYMBOL(dnfs_parse_remoteaddrs);
EXPORT_SYMBOL(dnfs_get_address_list);
EXPORT_SYMBOL(dnfs_free_address_list);
