// SPDX-License-Identifier: GPL-2.0-only
/*
 * fs/nfs/nfs_multipath.c -- Distributed NFS mount option parsing
 *
 * Copyright (c) 2026 Darren Starr <darren@example.com>
 *
 * Implements the "remoteaddrs=" mount option parser for client-side
 * NFSv4.1 multipath. This file is compiled into nfs.ko when
 * CONFIG_NFS_MULTIPATH is enabled.
 *
 * The remoteaddrs= option accepts a tilde-separated list of server
 * addresses. Each address is validated using rpc_pton() -- the same
 * function used by the stock NFS client to resolve server addresses.
 *
 * Example:
 *   mount -t nfs4 -o vers=4.1,remoteaddrs=10.0.0.1~10.0.0.2 \
 *       10.0.0.1:/export /mnt
 *
 * SECURITY
 *
 * The option parser is a critical security boundary. Malformed or
 * malicious mount option strings must never cause buffer overflows,
 * memory exhaustion, or invalid memory access. All input is bounded
 * and validated before any allocation occurs.
 *
 * - Input length bounded to 4096 bytes
 * - Token count bounded to CONFIG_NFS_MULTIPATH_MAX_ADDRS (default 32)
 * - Each address validated by rpc_pton() (kernel's NFS address parser)
 * - All allocations checked for failure
 */

#include <linux/kernel.h>
#include <linux/string.h>
#include <linux/slab.h>
#include <linux/errno.h>
#include <linux/sunrpc/addr.h>
#include <linux/nfs.h>

#include "internal.h"

/*
 * Maximum length of the remoteaddrs= option value.
 * Bounding this prevents resource exhaustion attacks.
 */
#define DNFS_MAX_OPTION_STRLEN 4096

/**
 * nfs_multipath_free_addrs - Free a parsed dnfs address list
 * @list:  The address list to free (may be NULL)
 *
 * Frees memory allocated during nfs_multipath_parse().
 * Safe to call with NULL.
 */
void nfs_multipath_free_addrs(struct nfs_multipath_addrs *list)
{
	kfree(list);
}

/**
 * nfs_multipath_parse - Parse remoteaddrs= mount option
 * @ctx:   NFS mount context (stores parsed result on success)
 * @value: Option value string (tilde-separated address list)
 *
 * Parses a tilde-separated list of server addresses and stores
 * the result in ctx->nfs_server.dnfs_remoteaddrs.
 *
 * The parser splits the input on tilde (~), skips empty tokens
 * (consecutive tildes), and passes each token through rpc_pton()
 * for address validation. Both IPv4 and IPv6 are supported.
 *
 * rpc_pton() handles:
 *   - IPv4 dotted decimal: "10.0.0.1"
 *   - IPv6 colon-hex:     "2001:db8::1"
 *   - IPv6 with brackets: "[2001:db8::1]"
 *   - Port notation:      "10.0.0.1:2049"
 *
 * Return: 0 on success, negative errno on failure:
 *   -EINVAL  Malformed option value or invalid address
 *   -E2BIG   Option value too long
 *   -ENOMEM  Memory allocation failure
 */
int nfs_multipath_parse(struct nfs_fs_context *ctx, const char *value)
{
	struct nfs_multipath_addrs *list;
	const char *p, *next;
	unsigned int count = 0, max_count;
	size_t val_len;
	int ret;

	/* Reject null or empty values immediately. */
	if (!value || !*value)
		return -EINVAL;

	/* Bounds-check the option value length. */
	val_len = strlen(value);
	if (val_len > DNFS_MAX_OPTION_STRLEN)
		return -E2BIG;

	/*
	 * First pass: count tilde-separated tokens.
	 * This lets us allocate exactly the right size.
	 */
	p = value;
	while (*p) {
		/* Skip leading and consecutive tildes. */
		while (*p == '~')
			p++;
		if (!*p)
			break;
		count++;
		if (count >= DNFS_MAX_ADDR_STRLEN)
			break;
		p = strchr(p, '~');
		if (!p)
			break;
		p++;
	}

	/* At least one address is required. */
	if (count == 0)
		return -EINVAL;

	/*
	 * Enforce the configured maximum.
	 * This prevents resource exhaustion attacks.
	 */
	max_count = CONFIG_NFS_MULTIPATH_MAX_ADDRS;
	if (count > max_count)
		return -E2BIG;

	/*
	 * Allocate the address list structure.
	 * The addrs[] array is variable-length at the end.
	 */
	list = kzalloc(sizeof(*list) + (count * sizeof(list->addrs[0])),
		       GFP_KERNEL);
	if (!list)
		return -ENOMEM;

	list->count = 0;
	list->max = count;

	/*
	 * Second pass: parse each address.
	 * Each token is validated via rpc_pton().
	 */
	p = value;
	while (*p && list->count < count) {
		size_t token_len;

		/* Skip leading and consecutive tildes. */
		while (*p == '~')
			p++;
		if (!*p)
			break;

		/* Find the end of this token. */
		next = strchr(p, '~');
		if (next)
			token_len = next - p;
		else
			token_len = strlen(p);

		/* Parse the address using kernel's NFS address parser. */
		if (!rpc_pton(&init_net, p, token_len,
			      (struct sockaddr *)&list->addrs[list->count],
			      sizeof(list->addrs[list->count]))) {
			pr_warn("NFS: nfs_multipath: invalid remote address '%.*s'\n",
				(int)token_len, p);
			ret = -EINVAL;
			goto out_free;
		}

		list->count++;

		/* Advance past this token. */
		if (next)
			p = next + 1;
		else
			break;
	}

	/* Store the parsed list in the mount context. */
	ctx->nfs_server.dnfs_remoteaddrs = list;
	return 0;

out_free:
	kfree(list);
	return ret;
}
