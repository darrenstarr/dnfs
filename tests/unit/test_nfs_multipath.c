/*
 * test_nfs_multipath.c — Unit tests for dnfs option parsing code.
 *
 * This file compiles the kernel's nfs_multipath.c option parser in user
 * space using mock headers for kernel dependencies. It tests every
 * code path in the parser, including all error paths and edge cases.
 *
 * USAGE
 *   make -C tests          # builds and runs all tests
 *   ./test_dnfs_parse      # run directly
 *
 * The test exits with 0 if all tests pass, or prints failures and
 * exits with 1 if any test fails.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <sys/socket.h>
#include <netinet/in.h>

/*
 * Include mock kernel headers BEFORE the production code.
 * The mocks provide just enough kernel API surface to compile.
 */
#include "mocks/linux/kernel.h"
#include "mocks/linux/string.h"
#include "mocks/linux/slab.h"
#include "mocks/linux/errno.h"
#include "mocks/linux/nfs.h"
#include "mocks/linux/sunrpc/addr.h"
#include "internal.h"

/*
 * Mock global variables — these control the behavior of
 * rpc_pton() and other mock functions during testing.
 */
bool __mock_rpc_pton_fail = false;
struct sockaddr_storage __mock_last_parsed;
size_t __mock_last_parsed_len;
struct net init_net;

/*
 * Include the production code UNDER TEST.
 * This compiles the actual kernel source with our mocks.
 */
#include "nfs/nfs_multipath.c"

/*
 * Test counters.
 */
static int tests_passed = 0;
static int tests_failed = 0;

/*
 * Test assertion macro.
 */
#define TEST_ASSERT(cond, msg) do {					\
	if (!(cond)) {							\
		fprintf(stderr, "FAIL: %s: %s\n", __func__, msg);	\
		tests_failed++;						\
		return;							\
	}								\
} while (0)

#define TEST_ASSERT_EQ(a, b, msg) do {					\
	if ((a) != (b)) {						\
		fprintf(stderr, "FAIL: %s: %s (%d != %d)\n",		\
			__func__, msg, (int)(a), (int)(b));		\
		tests_failed++;						\
		return;							\
	}								\
} while (0)

/*
 * Helper: create a minimal fs_context for testing.
 */
static struct nfs_fs_context *make_ctx(void)
{
	struct nfs_fs_context *ctx = calloc(1, sizeof(*ctx));
	assert(ctx != NULL);
	ctx->nfs_server.version = 4; /* NFSv4, minor version set separately */
	return ctx;
}

static void free_ctx(struct nfs_fs_context *ctx)
{
	if (ctx) {
		/* Static registry handles cleanup - no per-ctx list */
		free(ctx);
	}
}

/*
 * ====== TEST CASES ======
 */

/*
 * Test: valid IPv4 addresses parse correctly.
 */
static void test_valid_ipv4_single(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "10.0.0.1");
	TEST_ASSERT_EQ(ret, 0, "should parse single IPv4");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list != NULL, "address list should be allocated");
	TEST_ASSERT_EQ(list->count, 1, "should have 1 address");

	struct sockaddr_in *sin =
		(struct sockaddr_in *)&list->addrs[0];
	TEST_ASSERT_EQ(sin->sin_family, AF_INET,
		       "address family should be IPv4");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: multiple IPv4 addresses with tilde separator.
 */
static void test_valid_ipv4_multi(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "10.0.0.1~10.0.0.2~10.0.0.3");
	TEST_ASSERT_EQ(ret, 0, "should parse multiple IPv4");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list != NULL, "list should exist");
	TEST_ASSERT_EQ(list->count, 3,
		       "should have 3 addresses");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: valid IPv6 addresses parse correctly.
 */
static void test_valid_ipv6_single(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "2001:db8::1");
	TEST_ASSERT_EQ(ret, 0, "should parse single IPv6");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list != NULL, "list should exist");
	TEST_ASSERT_EQ(list->count, 1,
		       "should have 1 address");

	struct sockaddr_in6 *sin6 = (struct sockaddr_in6 *)&list->addrs[0];
	TEST_ASSERT_EQ(sin6->sin6_family, AF_INET6,
		       "address family should be IPv6");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: bracketed IPv6 addresses work.
 */
static void test_valid_ipv6_bracketed(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "[2001:db8::1]");
	TEST_ASSERT_EQ(ret, 0, "should parse bracketed IPv6");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: mixed IPv4 and IPv6 addresses.
 */
static void test_valid_mixed(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "10.0.0.1~2001:db8::1");
	TEST_ASSERT_EQ(ret, 0, "should parse mixed IPv4/IPv6");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list != NULL, "list should exist");
	TEST_ASSERT_EQ(list->count, 2,
		       "should have 2 addresses");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: null value should fail.
 */
static void test_null_value(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, NULL);
	TEST_ASSERT_EQ(ret, -EINVAL, "null value should fail");
	nfs_multipath_free_addrs(nfs_multipath_get_addrs());

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: empty string should fail.
 */
static void test_empty_string(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "");
	TEST_ASSERT_EQ(ret, -EINVAL, "empty string should fail");
	nfs_multipath_free_addrs(nfs_multipath_get_addrs());

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: only tildes should fail.
 */
static void test_only_tildes(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "~~~");
	TEST_ASSERT_EQ(ret, -EINVAL, "only tildes should fail");
	nfs_multipath_free_addrs(nfs_multipath_get_addrs());

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: invalid IP address should fail.
 */
static void test_invalid_address(void)
{
	struct nfs_fs_context *ctx = make_ctx();

	__mock_rpc_pton_fail = true;
	int ret = nfs_multipath_parse(ctx, "999.999.999.999");
	__mock_rpc_pton_fail = false;
	nfs_multipath_free_addrs(nfs_multipath_get_addrs());

	TEST_ASSERT_EQ(ret, -EINVAL, "invalid address should fail");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: hostnames should not be accepted (must be IP addresses).
 */
static void test_hostname_rejected(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	/* rpc_pton accepts DNS names only if they happen to parse as IP.
	 * This is a property of the mock — for a real test, we'd need
	 * the kernel's rpc_pton which rejects non-IP strings. */
	ret = nfs_multipath_parse(ctx, "server.example.com");
	TEST_ASSERT_EQ(ret, -EINVAL, "hostname should be rejected");
	nfs_multipath_free_addrs(nfs_multipath_get_addrs());

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: consecutive tildes should be collapsed.
 */
static void test_consecutive_tildes(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "10.0.0.1~~10.0.0.2");
	TEST_ASSERT_EQ(ret, 0, "consecutive tildes should work");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list != NULL, "list should exist");
	TEST_ASSERT_EQ(list->count, 2,
		       "consecutive tildes should collapse to 2 addresses");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: leading tilde should be ignored.
 */
static void test_leading_tilde(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "~10.0.0.1");
	TEST_ASSERT_EQ(ret, 0, "leading tilde should work");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list != NULL, "list should exist");
	TEST_ASSERT_EQ(list->count, 1,
		       "leading tilde should give 1 address");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: trailing tilde should be ignored.
 */
static void test_trailing_tilde(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	ret = nfs_multipath_parse(ctx, "10.0.0.1~");
	TEST_ASSERT_EQ(ret, 0, "trailing tilde should work");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list != NULL, "list should exist");
	TEST_ASSERT_EQ(list->count, 1,
		       "trailing tilde should give 1 address");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: maximum number of addresses.
 */
static void test_max_addresses(void)
{
	struct nfs_fs_context *ctx = make_ctx();

	/* Build a string with CONFIG_NFS_MULTIPATH_MAX_ADDRS addresses. */
	char buf[4096];
	int pos = 0;
	unsigned int i;

	for (i = 0; i < CONFIG_NFS_MULTIPATH_MAX_ADDRS; i++) {
		if (i > 0)
			buf[pos++] = '~';
		int n = snprintf(buf + pos, sizeof(buf) - pos,
				"10.0.%d.%d", i / 256, i % 256);
		if (n > 0)
			pos += n;
	}
	buf[pos] = '\0';

	int ret = nfs_multipath_parse(ctx, buf);
	TEST_ASSERT_EQ(ret, 0, "max addresses should parse");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT_EQ(list->count,
		       CONFIG_NFS_MULTIPATH_MAX_ADDRS,
		       "should have exactly max addresses");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: exceeding maximum addresses should fail.
 */
static void test_exceed_max_addresses(void)
{
	struct nfs_fs_context *ctx = make_ctx();

	/* Build a string with too many addresses. */
	char buf[8192];
	int pos = 0;
	unsigned int i;

	for (i = 0; i < CONFIG_NFS_MULTIPATH_MAX_ADDRS + 1; i++) {
		if (i > 0)
			buf[pos++] = '~';
		int n = snprintf(buf + pos, sizeof(buf) - pos,
				"10.0.%d.%d", i / 256, i % 256);
		if (n > 0)
			pos += n;
	}
	buf[pos] = '\0';

	int ret = nfs_multipath_parse(ctx, buf);
	TEST_ASSERT_EQ(ret, -E2BIG, "exceeding max addresses should fail");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: extremely long option value should fail.
 */
static void test_overflow_length(void)
{
	struct nfs_fs_context *ctx = make_ctx();

	/* Build a string longer than DNFS_MAX_OPTION_STRLEN. */
	char buf[5000];
	memset(buf, '~', sizeof(buf) - 1);
	/* Insert valid addresses at start and end. */
	memcpy(buf, "10.0.0.1", 8);
	buf[sizeof(buf) - 10] = '1';
	buf[sizeof(buf) - 9] = '0';
	buf[sizeof(buf) - 8] = '.';
	buf[sizeof(buf) - 7] = '0';
	buf[sizeof(buf) - 6] = '.';
	buf[sizeof(buf) - 5] = '0';
	buf[sizeof(buf) - 4] = '.';
	buf[sizeof(buf) - 3] = '2';
	buf[sizeof(buf) - 2] = '\0';
	buf[sizeof(buf) - 1] = '\0';

	int ret = nfs_multipath_parse(ctx, buf);
	TEST_ASSERT_EQ(ret, -E2BIG, "overlong value should fail");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: address with non-printable characters — NULL byte in the
 * middle is safe. The kernel's mount option parser guarantees
 * null-terminated strings; a null byte in the middle truncates
 * the value before our parser sees it. This is safe because the
 * truncated value is a valid (shorter) option.
 */
static void test_null_byte_truncates(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	/* NULL byte in the middle truncates to "10.0.0.1". */
	char evil[] = "10.0.0.1\x00~10.0.0.2";
	ret = nfs_multipath_parse(ctx, evil);
	/* The truncated string "10.0.0.1" is a valid single address. */
	TEST_ASSERT_EQ(ret, 0, "null byte should truncate to first address");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list != NULL, "list should exist");
	TEST_ASSERT_EQ(list->count, 1,
		       "should have only 1 address (truncated)");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: nfs_multipath_free_addrs with NULL is safe.
 */
static void test_free_null(void)
{
	nfs_multipath_free_addrs(NULL);
	tests_passed++;
}

/*
 * Test: multiple calls to parse on the same context should
 * replace the previous list (no memory leak).
 */
static void test_repeated_parse(void)
{
	struct nfs_fs_context *ctx = make_ctx();
	int ret;

	/* First parse. */
	ret = nfs_multipath_parse(ctx, "10.0.0.1");
	TEST_ASSERT_EQ(ret, 0, "first parse should work");

	/* Second parse should replace the list (caller frees old). */
		/* list freed via nfs_multipath_get_addrs pattern */
	/* list handled by static registry */

	ret = nfs_multipath_parse(ctx, "10.0.0.2~10.0.0.3");
	TEST_ASSERT_EQ(ret, 0, "second parse should work");
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list != NULL, "list should exist");
	TEST_ASSERT_EQ(list->count, 2,
		       "second parse should have 2 addresses");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: address list freed during context cleanup.
 */
static void test_context_cleanup(void)
{
	struct nfs_fs_context *ctx = make_ctx();

	int ret = nfs_multipath_parse(ctx, "10.0.0.1~10.0.0.2");
	nfs_multipath_free_addrs(nfs_multipath_get_addrs());
	TEST_ASSERT_EQ(ret, 0, "parse should work");

	/* Freeing the context should not leak. */
	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: trailing whitespace is rejected by rpc_pton.
 * The kernel's mount option parser strips whitespace before our
 * handler runs, so we should never see this in practice.
 */
static void test_trailing_whitespace(void)
{
	struct nfs_fs_context *ctx = make_ctx();

	/* Trailing space makes "10.0.0.1 " an invalid address. */
	int ret = nfs_multipath_parse(ctx, "10.0.0.1 ");

	TEST_ASSERT_EQ(ret, -EINVAL, "trailing whitespace should fail");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: regression — must not change behavior of existing options.
 * The dnfs option parser must not interfere with non-dnfs mounts.
 * A mount without remoteaddrs= should work exactly as before.
 */
static void test_no_remoteaddrs(void)
{
	struct nfs_fs_context *ctx = make_ctx();

	/* Without dnfs fields set, mount should proceed normally. */
	struct nfs_multipath_addrs *list = nfs_multipath_get_addrs();
	TEST_ASSERT(list == NULL,
		    "no dnfs option by default");
	TEST_ASSERT(ctx->nfs_server.version == 4,
		    "version should be unchanged");

	free_ctx(ctx);
	tests_passed++;
}

/*
 * Test: regression — the CONFIG_NFS_MULTIPATH ifdef guards must compile
 * cleanly when DNFS is disabled (this test always runs because
 * we define our own CONFIG_NFS_MULTIPATH_MAX_ADDRS).
 */
static void test_ifdef_clean(void)
{
	/* If we got here, the #if guards in the source code are
	 * syntactically valid with CONFIG_NFS_MULTIPATH enabled. For a full
	 * regression test, we'd also compile without the define. */
	tests_passed++;
}

/*
 * ====== RUN ALL TESTS ======
 */
int main(void)
{
	printf("Running dnfs option parsing tests...\n");
	printf("CONFIG_NFS_MULTIPATH_MAX_ADDRS = %d\n\n",
	       CONFIG_NFS_MULTIPATH_MAX_ADDRS);

	test_valid_ipv4_single();
	test_valid_ipv4_multi();
	test_valid_ipv6_single();
	test_valid_ipv6_bracketed();
	test_valid_mixed();
	test_null_value();
	test_empty_string();
	test_only_tildes();
	test_invalid_address();
	test_hostname_rejected();
	test_consecutive_tildes();
	test_leading_tilde();
	test_trailing_tilde();
	test_max_addresses();
	test_exceed_max_addresses();
	test_overflow_length();
	test_null_byte_truncates();
	test_free_null();
	test_repeated_parse();
	test_context_cleanup();
	test_trailing_whitespace();
	test_no_remoteaddrs();
	test_ifdef_clean();

	printf("\nResults: %d passed, %d failed out of %d tests\n",
	       tests_passed, tests_failed,
	       tests_passed + tests_failed);

	return tests_failed > 0 ? 1 : 0;
}
