/*
 * Mock kernel headers for user-space compilation of NFS option parsing code.
 *
 * These headers provide just enough of the kernel API surface to compile
 * dnfs_parse.c and the fs_context.c option parsing code in user space.
 *
 * Each mock either:
 *   (a) Wraps the equivalent user-space libc function (e.g., kmalloc → malloc)
 *   (b) Provides a minimal stub that does nothing (e.g., printk → /dev/null)
 *   (c) Provides a test-controllable mock (e.g., rpc_pton)
 *
 * SECURITY: These mocks intentionally do NOT replicate kernel behavior.
 * They only provide enough interface surface to make the code compile.
 * All security-relevant logic is in the production code itself.
 */

#ifndef _MOCK_LINUX_KERNEL_H
#define _MOCK_LINUX_KERNEL_H

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdbool.h>

/* Suppress unused variable warnings from kernel macros. */
#define __maybe_unused __attribute__((unused))
#define __must_check   __attribute__((warn_unused_result))
#define unlikely(x)    (x)
#define likely(x)      (x)

/* Kernel printk → test logging. */
#define KERN_DEBUG ""
#define KERN_INFO  ""
#define KERN_WARN  ""
#define KERN_ERR   ""

__attribute__((format(printf, 1, 2)))
static inline int printk(const char *fmt, ...) {
	va_list args;
	int ret;
	va_start(args, fmt);
	ret = vfprintf(stderr, fmt, args);
	va_end(args);
	return ret;
}

#define pr_debug(fmt, ...) printk(KERN_DEBUG fmt, ##__VA_ARGS__)
#define pr_info(fmt, ...)  printk(KERN_INFO fmt, ##__VA_ARGS__)
#define pr_warn(fmt, ...)  printk(KERN_WARN fmt, ##__VA_ARGS__)
#define pr_err(fmt, ...)   printk(KERN_ERR fmt, ##__VA_ARGS__)

/* Kernel memory allocation → libc malloc/free. */
#define GFP_KERNEL  (0)
#define __GFP_ZERO  (1)

static inline void *kmalloc(size_t size, int flags) {
	(void)flags;
	return malloc(size);
}

static inline void *kzalloc(size_t size, int flags) {
	(void)flags;
	return calloc(1, size);
}

static inline void kfree(void *p) {
	free(p);
}

/* Size calculation macro for variable-length structs. */
#define struct_size(ptr, member, count) \
	(sizeof(*(ptr)) + (count) * sizeof((ptr)->member[0]))

/* Atomic types — not needed for parsing tests. */
typedef struct { int counter; } atomic_t;

static inline int atomic_read(const atomic_t *v) { return v->counter; }
static inline void atomic_set(atomic_t *v, int i) { v->counter = i; }

/* Kernel types that map to C standard types. */
typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef unsigned long long u64;
typedef int32_t  s32;
typedef int64_t  s64;
typedef u32 __be32;
typedef u16 __be16;

/* NULL/ERR_PTR macros. */
#define IS_ERR_VALUE(x) ((unsigned long)(void *)(x) >= (unsigned long)-4095)
static inline void *ERR_PTR(long err)  { return (void *)err; }
static inline long  PTR_ERR(const void *p) { return (long)p; }
static inline bool  IS_ERR(const void *p)  { return IS_ERR_VALUE(p); }
static inline bool  IS_ERR_OR_NULL(const void *p) { return !p || IS_ERR(p); }

/* Min/max macros. */
#define min(a, b) ({ \
	typeof(a) _a = (a); typeof(b) _b = (b); _a < _b ? _a : _b; })
#define max(a, b) ({ \
	typeof(a) _a = (a); typeof(b) _b = (b); _a > _b ? _a : _b; })

#endif /* _MOCK_LINUX_KERNEL_H */
