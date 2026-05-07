#ifndef _MOCK_LINUX_MUTEX_H
#define _MOCK_LINUX_MUTEX_H
typedef struct { int dummy; } mutex_t;
#define DEFINE_MUTEX(name) mutex_t name = {0}
static inline void mutex_lock(mutex_t *m) { (void)m; }
static inline void mutex_unlock(mutex_t *m) { (void)m; }
#endif
