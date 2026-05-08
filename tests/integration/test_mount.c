/*
 * test_mount.c — Basic NFS mount via syscall
 */
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/mount.h>

int main(int argc, char **argv)
{
	const char *opts = argc > 1 ? argv[1] : "vers=4.1,hard,timeo=600,rsize=1048576,wsize=1048576,clientaddr=127.0.0.1,local_lock=none";
	int ret = mount("localhost:/", "/mnt-test", "nfs4", 0, opts);
	if (ret < 0) {
		printf("FAIL: %s (errno=%d)\n", strerror(errno), errno);
		return 1;
	}
	printf("MOUNT OK\n");
	return 0;
}
