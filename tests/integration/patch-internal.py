#!/usr/bin/env python3
"""Patch internal.h to add dnfs fields to nfs_fs_context."""
import sys
import re

with open('internal.h') as f:
    content = f.read()

# Add struct nfs_multipath_addrs before NFS_SUPER_MAGIC if not present
if 'dnfs_address_list' not in content:
    content = re.sub(
        r'(#define NFS_SUPER_MAGIC)',
        r'struct nfs_multipath_addrs {\n\tunsigned int count;\n\tunsigned int max;\n\tstruct sockaddr_storage addrs[];\n};\n\n\1',
        content
    )

# Find the nfs_fs_context struct and add dnfs fields after the version field
# We look for: struct nfs_fs_context { ... hostname; version; port; ... }
if 'dnfs_remoteaddrs' not in content:
    # Find the nfs_fs_context block
    m = re.search(r'struct nfs_fs_context \{[^}]*\}', content, re.DOTALL)
    if m:
        block = m.group()
        # Find the first occurrence of 'char *hostname;' followed by version field
        sub = re.search(r'(char\s*\*\s*hostname\s*;\s*\n\s*u32\s+version\s*;)', block)
        if sub:
            replacement = sub.group(1) + '\n\t\tstruct nfs_multipath_addrs *dnfs_remoteaddrs;\n\t\tbool dnfs_parsed;'
            content = content.replace(sub.group(1), replacement)
            print('Added dnfs fields after hostname/version')
        else:
            # Fallback: add after any version field in nfs_fs_context
            sub2 = re.search(r'(struct nfs_fs_context \{.*?)(u32\s+version\s*;)', content, re.DOTALL)
            if sub2:
                replacement = sub2.group(2) + '\n\tstruct nfs_multipath_addrs *dnfs_remoteaddrs;\n\tbool dnfs_parsed;'
                content = content.replace(sub2.group(2), replacement)
                print('Added dnfs fields (fallback)')
            else:
                print('ERROR: Could not find version field in nfs_fs_context')
                sys.exit(1)

with open('internal.h', 'w') as f:
    f.write(content)

# Verify
with open('internal.h') as f:
    c = f.read()
if 'dnfs_remoteaddrs' in c:
    print('Verified: dnfs_remoteaddrs is present')
else:
    print('ERROR: dnfs_remoteaddrs was not added')
    sys.exit(1)
