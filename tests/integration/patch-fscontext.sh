#!/bin/bash
# Patch fs_context.c to add remoteaddrs mount option
set -e
cd /home/cave/kernel-build/linux-source-7.0.0/fs/nfs || exit 1

# Add to enum (after Opt_rdma = line 78)
sed -i '78 a\
\tOpt_remoteaddrs,\\\
\tOpt_localaddrs,' fs_context.c

# Fix the sed - it should be after Opt_rdma line which shifted
# Add fsparam entries (after rdma fsparam)
sed -i '204 a\
\tfsparam_string("remoteaddrs",	Opt_remoteaddrs),\\"
\tfsparam_string("localaddrs",	Opt_localaddrs),' fs_context.c

# Add case handler in parse function (after Opt_rdma case block)
# Find the right insertion point
sed -i '/case Opt_rdma:/a\
\tcase Opt_remoteaddrs:\
\t\treturn 0;\
\tcase Opt_localaddrs:\
\t\treturn 0;' fs_context.c

echo "fs_context.c patched"
grep -n 'Opt_remoteaddrs\|Opt_localaddrs' fs_context.c
