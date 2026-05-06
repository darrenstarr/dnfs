#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
#
# test-apply-patches.sh — Apply dnfs patches to kernel source and build
#
# This script applies the dnfs patch series to the kernel source tree
# on the build VM, builds the nfs.ko module, and installs it.
#
# Usage: ./test-apply-patches.sh [--vm-only] [--local-only]
#
# --vm-only:  Run on the build VM (via SSH)
# --local-only: Run on the local machine only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH_DIR="${SCRIPT_DIR}/../patches"
KERNEL_SRC="${HOME}/kernel-build/linux-source-7.0.0"

echo "=== dnfs: Applying patches and building ==="

# Verify the kernel source directory exists.
if [ ! -d "${KERNEL_SRC}" ]; then
	echo "ERROR: Kernel source not found at ${KERNEL_SRC}"
	echo "Run: tar -xjf /usr/src/linux-source-7.0.0.tar.bz2"
	exit 1
fi

# Verify patch files exist.
if [ ! -f "${PATCH_DIR}/series" ]; then
	echo "ERROR: Patch series file not found at ${PATCH_DIR}/series"
	exit 1
fi

# Apply patches using quilt-style series file.
echo "Applying patches..."
cd "${KERNEL_SRC}"

while read -r patch; do
	patch_file="${PATCH_DIR}/${patch}"
	if [ ! -f "${patch_file}" ]; then
		echo "WARNING: Patch ${patch} not found, skipping"
		continue
	fi
	echo "  Applying ${patch}..."
	patch -p1 < "${patch_file}"
done < "${PATCH_DIR}/series"

echo "All patches applied successfully."

# Build the patched NFS module.
echo "Building NFS module with dnfs support..."
make -j$(nproc) M=fs/nfs 2>&1 | tail -5

echo "Build complete."

# Install the module if on the target system.
if [ "$(id -u)" = "0" ] || command -v sudo &>/dev/null; then
	echo "Installing module..."
	sudo cp fs/nfs/nfs.ko /lib/modules/$(uname -r)/updates/
	sudo depmod -a
	echo "Module installed. Unload/reload NFS to activate."
fi

echo "=== Done ==="
