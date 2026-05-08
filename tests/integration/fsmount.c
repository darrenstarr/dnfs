/*
 * fsmount test — use new mount API to bypass mount.nfs4
 * gcc -o fsmount fsmount.c
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <fcntl.h>
#include <errno.h>

/* New mount API syscalls */
#ifndef __NR_fsopen
#define __NR_fsopen 430
#endif
#ifndef __NR_fsconfig
#define __NR_fsconfig 431
#endif
#ifndef __NR_fsmount
#define __NR_fsmount 432
#endif

enum {
	FSCONFIG_SET_FLAG = 0,
	FSCONFIG_SET_STRING = 1,
};

static int fsopen(const char *name, unsigned int flags) {
	return syscall(__NR_fsopen, name, flags);
}
static int fsconfig(int fd, unsigned int cmd, const char *key,
		    const char *val, int aux) {
	return syscall(__NR_fsconfig, fd, cmd, key, val, aux);
}
static int fsmount(int fd, unsigned int flags, unsigned int attrs) {
	return syscall(__NR_fsmount, fd, flags, attrs);
}

int main(int argc, char **argv)
{
	const char *addrs = argc > 1 ? argv[1] : "127.0.0.1~127.0.0.2";
	int fd, ret;
	int verb = argc > 2 ? atoi(argv[2]) : 1;

	fd = fsopen("nfs4", 0);
	if (fd < 0) { perror("fsopen"); return 1; }

	if (verb) printf("fsopen fd=%d\n", fd);

	/* Set source */
	ret = fsconfig(fd, FSCONFIG_SET_STRING, "source", "localhost:/", 0);
	if (ret < 0) { perror("source"); close(fd); return 1; }

	/* Set version */
	ret = fsconfig(fd, FSCONFIG_SET_STRING, "vers", "4.1", 0);
	if (ret < 0) { perror("vers"); close(fd); return 1; }

	/* Set protocol */
	ret = fsconfig(fd, FSCONFIG_SET_STRING, "proto", "tcp", 0);
	if (ret < 0) { perror("proto"); close(fd); return 1; }

	/* Set multipath addresses */
	ret = fsconfig(fd, FSCONFIG_SET_STRING, "remoteaddrs", addrs, 0);
	if (ret < 0) { perror("remoteaddrs"); close(fd); return 1; }

	/* Hard mount */
	ret = fsconfig(fd, FSCONFIG_SET_FLAG, "hard", NULL, 0);
	if (ret < 0) { perror("hard"); close(fd); return 1; }

	/* Timeo */
	ret = fsconfig(fd, FSCONFIG_SET_STRING, "timeo", "600", 0);
	if (ret < 0) { perror("timeo"); close(fd); return 1; }

	/* Create the superblock */
	ret = fsconfig(fd, 6, NULL, NULL, 0);
	if (ret < 0) {
		if (errno == EINVAL)
			printf("CREATE failed — unprocessed options remain\n");
		else
			perror("create");
		close(fd);
		return 1;
	}

	/* Mount */
	int mfd = fsmount(fd, 0, 0);
	if (mfd < 0) { perror("fsmount"); close(fd); return 1; }

	printf("MOUNT OK fd=%d mfd=%d\n", fd, mfd);
	close(fd);
	close(mfd);
	return 0;
}
