/*
 * mount_mpath.c — Direct mount(2) call with remoteaddrs= option.
 * Uses the exact same options as mount.nfs4 but adds remoteaddrs=.
 *
 * gcc -o mount_mpath mount_mpath.c
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/mount.h>

int main(int argc, char **argv)
{
	const char *addrs = argc > 1 ? argv[1] : "127.0.0.1~127.0.0.2";
	const char *mntpt = argc > 2 ? argv[2] : "/mnt-mpath";
	char opts[4096];

	snprintf(opts, sizeof(opts),
		"sloppy,vers=4.1,hard,timeo=600,retrans=2,"
		"rsize=1048576,wsize=1048576,proto=tcp,"
		"clientaddr=127.0.0.1,local_lock=none,"
		"remoteaddrs=%s",
		addrs);

	printf("mount options: %s\n", opts);

	int ret = mount("localhost:/", mntpt, "nfs4", 0, opts);
	if (ret < 0) {
		printf("FAIL: %s (errno=%d)\n", strerror(errno), errno);
		return 1;
	}
	printf("MOUNT OK\n");
	return 0;
}
