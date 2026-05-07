// SPDX-License-Identifier: GPL-2.0-only
#include <linux/kernel.h>
#include <linux/string.h>
#include <linux/slab.h>
#include <linux/errno.h>
#include <linux/sunrpc/addr.h>
#include <linux/mutex.h>
#include "nfs_multipath.h"

#define MAX_OPT_STRLEN 4096

static struct nfs_multipath_addrs *g_addrs;
static DEFINE_MUTEX(g_addrs_lock);

int nfs_multipath_parse(void *unused, const char *value)
{
	struct nfs_multipath_addrs *list;
	int count = 0;
	int i;
	size_t val_len;
	const char *s;

	if (!value) return -EINVAL;
	val_len = strlen(value);
	if (val_len > MAX_OPT_STRLEN) return -E2BIG;
	if (val_len == 0) return -EINVAL;

	for (s = value; *s; s++) {
		if (*s == '~') count++;
	}
	count++; /* last token after the final tilde */

	if (count > CONFIG_NFS_MULTIPATH_MAX_ADDRS) return -E2BIG;

	list = kzalloc(sizeof(*list) + count * sizeof(list->addrs[0]), GFP_KERNEL);
	if (!list) return -ENOMEM;

	s = value;
	for (i = 0; i < count; i++) {
		const char *end = strchr(s, '~');
		size_t len = end ? (size_t)(end - s) : strlen(s);
		while (len > 0 && *s == '~') { s++; len--; }
		if (len == 0) { count--; i--; s++; continue; }

		if (!rpc_pton(&init_net, s, len,
			(struct sockaddr *)&list->addrs[i],
			sizeof(list->addrs[i]))) {
			kfree(list);
			return -EINVAL;
		}
		list->count++;
		s = end ? end + 1 : s + len;
	}

	if (list->count == 0) { kfree(list); return -EINVAL; }

	mutex_lock(&g_addrs_lock);
	kfree(g_addrs);
	g_addrs = list;
	mutex_unlock(&g_addrs_lock);
	return 0;
}

struct nfs_multipath_addrs *nfs_multipath_get_addrs(void)
{
	struct nfs_multipath_addrs *list;
	mutex_lock(&g_addrs_lock);
	list = g_addrs;
	g_addrs = NULL;
	mutex_unlock(&g_addrs_lock);
	return list;
}

void nfs_multipath_free_addrs(struct nfs_multipath_addrs *list)
{
	kfree(list);
}

EXPORT_SYMBOL(nfs_multipath_parse);
EXPORT_SYMBOL(nfs_multipath_get_addrs);
EXPORT_SYMBOL(nfs_multipath_free_addrs);
