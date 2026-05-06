/*
 * Mock for linux/string.h — delegates to user-space string.h.
 * Only defines kernel string functions that differ from libc.
 */
#ifndef _MOCK_LINUX_STRING_H
#define _MOCK_LINUX_STRING_H

#include <string.h>
#include <errno.h>

/* strscpy is like strncpy but always null-terminates and returns
 * the number of bytes copied (excluding null). For our test purposes,
 * it's equivalent to snprintf. */
static inline int strscpy(char *dst, const char *src, size_t dlen) {
	if (dlen == 0) return -E2BIG;
	size_t slen = strlen(src);
	if (slen >= dlen) return -E2BIG;
	memcpy(dst, src, slen + 1);
	return (int)slen;
}

#endif /* _MOCK_LINUX_STRING_H */
