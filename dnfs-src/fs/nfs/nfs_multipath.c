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

	/* DEBUG: entry */
	printk(KERN_CRIT "mpath: entry value=%s\n", value ? value : "NULL");

	if (!value) { printk(KERN_CRIT "mpath: null value\n"); return -EINVAL; }
	val_len = strlen(value);
	if (val_len > MAX_OPT_STRLEN) { printk(KERN_CRIT "mpath: too long %zu\n", val_len); return -E2BIG; }
	if (val_len == 0) { printk(KERN_CRIT "mpath: empty\n"); return -EINVAL; }

	for (s = value; *s; s++) {
		if (*s == '~') count++;
	}
	count++;
	printk(KERN_CRIT "mpath: token count=%d\n", count);

	if (count > CONFIG_NFS_MULTIPATH_MAX_ADDRS) { printk(KERN_CRIT "mpath: too many tokens\n"); return -E2BIG; }

	list = kzalloc(sizeof(*list) + count * sizeof(list->addrs[0]), GFP_KERNEL);
	if (!list) { printk(KERN_CRIT "mpath: alloc fail\n"); return -ENOMEM; }

	s = value;
	for (i = 0; i < count; i++) {
		const char *end = strchr(s, '~');
		size_t len = end ? (size_t)(end - s) : strlen(s);

		while (len > 0 && *s == '~') { s++; len--; }
		if (len == 0) { count--; i--; s++; continue; }

		printk(KERN_CRIT "mpath: parsing addr %d: %.*s (len=%zu)\n", i, (int)len, s, len);

		if (!rpc_pton(&init_net, s, len,
			(struct sockaddr *)&list->addrs[i],
			sizeof(list->addrs[i]))) {
			printk(KERN_CRIT "mpath: rpc_pton failed for %.*s\n", (int)len, s);
			kfree(list);
			return -EINVAL;
		}
		list->count++;
		s = end ? end + 1 : s + len;
	}

	if (list->count == 0) { printk(KERN_CRIT "mpath: no valid addrs\n"); kfree(list); return -EINVAL; }

	mutex_lock(&g_addrs_lock);
	kfree(g_addrs);
	g_addrs = list;
	mutex_unlock(&g_addrs_lock);
	printk(KERN_CRIT "mpath: stored %d addrs\n", list->count);
	return 0;
}

struct nfs_multipath_addrs *nfs_multipath_get_addrs(void)
{
	struct nfs_multipath_addrs *list;
	mutex_lock(&g_addrs_lock);
	list = g_addrs;
	g_addrs = NULL;
	mutex_unlock(&g_addrs_lock);
	if (list) printk(KERN_CRIT "mpath: consumed %d addrs\n", list->count);
	return list;
}

void nfs_multipath_free_addrs(struct nfs_multipath_addrs *list)
{
	if (list) printk(KERN_CRIT "mpath: freeing %d addrs\n", list->count);
	kfree(list);
}

EXPORT_SYMBOL(nfs_multipath_parse);
EXPORT_SYMBOL(nfs_multipath_get_addrs);
EXPORT_SYMBOL(nfs_multipath_free_addrs);
