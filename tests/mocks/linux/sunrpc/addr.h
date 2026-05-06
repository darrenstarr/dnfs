/*
 * Mock for linux/sunrpc/addr.h — provides rpc_pton for testing.
 *
 * In production, rpc_pton() is the kernel's NFS address parser.
 * For testing, we provide a configurable mock that can be set to
 * accept or reject addresses as needed for each test case.
 *
 * The mock validates basic IPv4/IPv6 syntax and stores the result
 * in the provided sockaddr_storage.
 */
#ifndef _MOCK_SUNRPC_ADDR_H
#define _MOCK_SUNRPC_ADDR_H

#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <string.h>
#include <stdbool.h>

/* Mock control: when set to false, rpc_pton returns 0 (parse failure). */
extern bool __mock_rpc_pton_fail;

/* Mock control: when set, records the last parsed address for test inspection. */
extern struct sockaddr_storage __mock_last_parsed;
extern size_t __mock_last_parsed_len;

/* Default network namespace — we use a global for testing. */
struct net {
	int dummy;
};
extern struct net init_net;

/**
 * rpc_pton — Mock for kernel's NFS address parser.
 * @net:  Network namespace (unused in mock)
 * @addr: Address string
 * @len:  Length of address string
 * @sa:   Output sockaddr
 * @salen: Size of output buffer
 *
 * Returns: Length of sockaddr on success, 0 on failure.
 *
 * The mock delegates to inet_pton for IPv4 and IPv6.
 * It also accepts bracketed IPv6 (e.g., "[::1]").
 */
static inline size_t rpc_pton(struct net *net,
			      const char *addr, size_t len,
			      struct sockaddr *sa, size_t salen)
{
	(void)net;
	(void)salen;

	char buf[64];
	size_t copylen = len < sizeof(buf) - 1 ? len : sizeof(buf) - 1;

	memcpy(buf, addr, copylen);
	buf[copylen] = '\0';

	if (__mock_rpc_pton_fail)
		return 0;

	/* Try IPv4 first. */
	struct sockaddr_in *sin = (struct sockaddr_in *)sa;
	memset(sin, 0, sizeof(*sin));
	if (inet_pton(AF_INET, buf, &sin->sin_addr) == 1) {
		sin->sin_family = AF_INET;
		sin->sin_port = htons(2049); /* Default NFS port */
		__mock_last_parsed_len = sizeof(*sin);
		memcpy(&__mock_last_parsed, sa, sizeof(*sin));
		return sizeof(*sin);
	}

	/* Try IPv6, stripping brackets if present. */
	if (buf[0] == '[') {
		size_t blen = strlen(buf);
		if (blen > 2 && buf[blen - 1] == ']') {
			buf[blen - 1] = '\0';
			memmove(buf, buf + 1, blen - 1);
		}
	}

	struct sockaddr_in6 *sin6 = (struct sockaddr_in6 *)sa;
	memset(sin6, 0, sizeof(*sin6));
	if (inet_pton(AF_INET6, buf, &sin6->sin6_addr) == 1) {
		sin6->sin6_family = AF_INET6;
		sin6->sin6_port = htons(2049);
		__mock_last_parsed_len = sizeof(*sin6);
		memcpy(&__mock_last_parsed, sa, sizeof(*sin6));
		return sizeof(*sin6);
	}

	return 0;
}

#endif /* _MOCK_SUNRPC_ADDR_H */
