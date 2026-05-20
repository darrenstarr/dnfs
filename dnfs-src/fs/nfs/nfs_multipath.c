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
static struct nfs_multipath_addrs *g_local_addrs;
static DEFINE_MUTEX(g_addrs_lock);

static int parse_addr_list(const char *value, struct nfs_multipath_addrs **dst)
{
	struct nfs_multipath_addrs *list;
	const char *p, *next;
	unsigned int count = 0, max_count;
	int ret;

	if (!value || !*value)
		return -EINVAL;

	if (strlen(value) > MAX_OPT_STRLEN)
		return -E2BIG;

	p = value;
	while (*p) {
		while (*p == '~')
			p++;
		if (!*p)
			break;
		count++;
		p = strchr(p, '~');
		if (!p)
			break;
		p++;
	}

	if (count == 0)
		return -EINVAL;

	max_count = CONFIG_NFS_MULTIPATH_MAX_ADDRS;
	if (count > max_count)
		return -E2BIG;

	list = kzalloc(sizeof(*list) + (count * sizeof(list->addrs[0])), GFP_KERNEL);
	if (!list)
		return -ENOMEM;

	list->count = 0;
	list->max = count;

	p = value;
	while (*p && list->count < count) {
		size_t token_len;

		while (*p == '~')
			p++;
		if (!*p)
			break;

		next = strchr(p, '~');
		if (next)
			token_len = next - p;
		else
			token_len = strlen(p);

		if (!rpc_pton(&init_net, p, token_len,
			      (struct sockaddr *)&list->addrs[list->count],
			      sizeof(list->addrs[list->count]))) {
			pr_warn("NFS multipath: bad addr '%.*s'\n", (int)token_len, p);
			ret = -EINVAL;
			goto out_free;
		}
		list->count++;

		if (next)
			p = next + 1;
		else
			break;
	}

	mutex_lock(&g_addrs_lock);
	kfree(*dst);
	*dst = list;
	mutex_unlock(&g_addrs_lock);
	pr_info("mpath: stored %d addrs\n", list->count);
	return 0;

out_free:
	kfree(list);
	return ret;
}

int nfs_multipath_parse(void *unused, const char *value)
{
	pr_info("mpath: entry value=%s\n", value);
	return parse_addr_list(value, &g_addrs);
}

int nfs_multipath_parse_local(void *unused, const char *value)
{
	pr_info("mpath: localaddrs value=%s\n", value);
	return parse_addr_list(value, &g_local_addrs);
}

static struct nfs_multipath_addrs *get_and_clear(struct nfs_multipath_addrs **p)
{
	struct nfs_multipath_addrs *list;
	mutex_lock(&g_addrs_lock);
	list = *p;
	*p = NULL;
	mutex_unlock(&g_addrs_lock);
	if (list)
		pr_info("mpath: consumed %d addrs\n", list->count);
	return list;
}

struct nfs_multipath_addrs *nfs_multipath_get_addrs(void)
{
	return get_and_clear(&g_addrs);
}
EXPORT_SYMBOL(nfs_multipath_get_addrs);

struct nfs_multipath_addrs *nfs_multipath_get_local_addrs(void)
{
	return get_and_clear(&g_local_addrs);
}
EXPORT_SYMBOL(nfs_multipath_get_local_addrs);

void nfs_multipath_free_addrs(struct nfs_multipath_addrs *list)
{
	if (list)
		pr_info("mpath: freeing %d addrs\n", list->count);
	kfree(list);
}
EXPORT_SYMBOL(nfs_multipath_free_addrs);
