#!/usr/bin/env python3
"""Fix Makefile: add dnfs_parse.o to the nfs-y source list."""
import sys

with open('Makefile') as f:
    lines = f.readlines()

with open('Makefile', 'w') as f:
    for l in lines:
        f.write(l)
        if l.strip().startswith('nfs-y') and 'client.o' in l:
            f.write('\t\t\t   dnfs_parse.o \\\n')

print("Makefile patched")
