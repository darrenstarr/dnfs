/*
 * preload.c — LD_PRELOAD library to add remoteaddrs= to NFS mount options
 * Compile: gcc -shared -fPIC -o preload.so preload.c -ldl
 * Use: LD_PRELOAD=/path/to/preload.so mount -t nfs4 -o ... localhost:/ /mnt
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <sys/mount.h>

/* The mount options we want to inject */
static const char *extra_opts = NULL;

/* Read extra options from environment */
static void init_extra(void)
{
    if (!extra_opts)
        extra_opts = getenv("NFS_EXTRA_OPTS");
    if (!extra_opts)
        extra_opts = "";
}

int mount(const char *source, const char *target,
          const char *filesystemtype, unsigned long mountflags,
          const void *data)
{
    static int (*real_mount)(const char *, const char *,
                             const char *, unsigned long,
                             const void *) = NULL;
    char *new_data = NULL;
    int ret;

    init_extra();

    if (!real_mount)
        real_mount = (int (*)(const char *, const char *,
                              const char *, unsigned long,
                              const void *))dlsym(RTLD_NEXT, "mount");

    /* Only inject for NFS mounts that have our option */
    if (filesystemtype && strstr(filesystemtype, "nfs") && *extra_opts) {
        if (data) {
            size_t dlen = strlen((const char *)data);
            size_t elen = strlen(extra_opts);
            new_data = malloc(dlen + elen + 2);
            if (new_data) {
                memcpy(new_data, data, dlen);
                new_data[dlen] = ',';
                memcpy(new_data + dlen + 1, extra_opts, elen + 1);
            }
        } else {
            new_data = strdup(extra_opts);
        }
    }

    ret = real_mount(source, target, filesystemtype, mountflags,
                     new_data ? new_data : data);
    free(new_data);
    return ret;
}
