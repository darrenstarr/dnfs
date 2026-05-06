#ifndef _MOCK_LINUX_ERRNO_H
#define _MOCK_LINUX_ERRNO_H
#include <errno.h>
/* Ensure all kernel errno values are available for compilation.
 * These match the kernel's asm-generic/errno-base.h values. */
#ifndef EINVAL
#define EINVAL 22
#endif
#ifndef ENOMEM
#define ENOMEM 12
#endif
#ifndef E2BIG
#define E2BIG  7
#endif
#ifndef EOPNOTSUPP
#define EOPNOTSUPP 95
#endif
#ifndef ECONNREFUSED
#define ECONNREFUSED 111
#endif
#ifndef ENETUNREACH
#define ENETUNREACH 101
#endif
#endif
