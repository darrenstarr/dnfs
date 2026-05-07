#!/usr/bin/env python3
"""Update fs_context.c to call dnfs parser on Opt_remoteaddrs."""
import re, sys

with open('fs_context.c') as f:
    c = f.read()

old = 'case Opt_remoteaddrs:\n\tcase Opt_localaddrs:\n\t\treturn 0;'
new = 'case Opt_remoteaddrs:\n\t\treturn nfs_multipath_parse(NULL, param->string);\n\tcase Opt_localaddrs:\n\t\treturn 0;'

if old in c:
    c = c.replace(old, new)
    with open('fs_context.c', 'w') as f:
        f.write(c)
    print('fs_context.c: updated Opt_remoteaddrs handler')
else:
    print('fs_context.c: pattern not found')
    # Debug: show what's around Opt_remoteaddrs
    for i, l in enumerate(open('fs_context.c').readlines()):
        if 'Opt_remoteaddrs' in l:
            print(f'  L{i+1}: {l.rstrip()}')
