#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
#
# test-nfs-server-setup.sh — Set up an NFSv4.1 server for testing
#
# Creates a local NFS server with a test export for running dnfs
# integration tests. Designed to run on the test VM (nfsdev). 
# Requires root privileges.
#
# USAGE
#   sudo ./test-nfs-server-setup.sh [start|stop|status]

set -euo pipefail

EXPORT_DIR="/export"
EXPORT_OPTS="*(rw,fsid=0,insecure,no_subtree_check,no_root_squash)"

case "${1:-start}" in
start)
	echo "=== Setting up NFSv4.1 test server ==="

	# Create export directory if it doesn't exist.
	mkdir -p "${EXPORT_DIR}"
	chmod 777 "${EXPORT_DIR}"

	# Add to /etc/exports if not already present.
	if ! grep -q "${EXPORT_DIR}" /etc/exports 2>/dev/null; then
		echo "${EXPORT_DIR} ${EXPORT_OPTS}" >> /etc/exports
		echo "Added ${EXPORT_DIR} to /etc/exports"
	fi

	# Mount nfsd filesystem (for NFSv4).
	if ! mountpoint -q /proc/fs/nfsd 2>/dev/null; then
		mount -t nfsd nfsd /proc/fs/nfsd
	fi

	# Start nfsd kernel threads.
	echo "Starting nfsd kernel threads..."
	echo 8 > /proc/fs/nfsd/threads 2>/dev/null || true

	# Export the filesystem.
	exportfs -ra
	echo "Exports:"
	exportfs -v

	# Verify nfsd is running.
	if lsmod | grep -q nfsd; then
		echo "nfsd module loaded"
	else
		modprobe nfsd
	fi

	echo "=== NFSv4.1 test server ready ==="
	echo "Export: ${EXPORT_DIR}"
	echo "Options: ${EXPORT_OPTS}"
	echo ""
	echo "Run tests with: TEST_SERVER=localhost ./test-multipath-mount.sh"
	;;

stop)
	echo "=== Stopping NFS test server ==="
	exportfs -ua
	echo 0 > /proc/fs/nfsd/threads 2>/dev/null || true
	umount -f /proc/fs/nfsd 2>/dev/null || true
	echo "Stopped."
	;;

status)
	echo "=== NFS server status ==="
	if lsmod | grep -q nfsd; then
		echo "nfsd: loaded"
	else
		echo "nfsd: not loaded"
	fi
	echo "Exports:"
	exportfs -v 2>/dev/null || echo "  (none)"
	echo "Mounts:"
	mount | grep nfs || echo "  (none)"
	;;

*)
	echo "Usage: $0 [start|stop|status]"
	exit 1
	;;
esac
