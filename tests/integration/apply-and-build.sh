#!/bin/bash
# apply-and-build.sh — Apply dnfs patches and build on VM
set -euo pipefail

KERNEL_SRC="${HOME}/kernel-build/linux-source-7.0.0"
PATCH_DIR="${HOME}/kernel-build/patches"
NEW_FILE="${HOME}/kernel-build/fs/nfs/nfs_multipath.c"

cd "${KERNEL_SRC}"

# Apply patches from the series file.
echo "Applying patches..."
while read -r patch; do
	patch_file="${PATCH_DIR}/${patch}"
	if [ -f "${patch_file}" ]; then
		echo "  ${patch}"
		patch -p1 < "${patch_file}"
	else
		echo "  WARNING: ${patch} not found, skipping"
	fi
done < "${PATCH_DIR}/series"

# Copy the new source file into the kernel tree.
if [ -f "${NEW_FILE}" ]; then
	cp "${NEW_FILE}" fs/nfs/
	echo "Copied nfs_multipath.c"
fi

# Configure and build.
echo "Configuring..."
cp "/boot/config-$(uname -r)" .config
make olddefconfig 2>&1 | tail -1
echo '-14-generic' > localversion-ubuntu

echo "Building NFS module..."
make -j"$(nproc)" M=fs/nfs 2>&1 | tail -5

echo "BUILD COMPLETE"
ls -la fs/nfs/nfs.ko
modinfo fs/nfs/nfs.ko | grep -E 'filename|vermagic'
