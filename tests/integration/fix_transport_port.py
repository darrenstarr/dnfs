#!/usr/bin/env python3
"""Fix transport creation hook in nfs4proc.c to set port and addrlen."""
import os, re

os.chdir(os.path.expanduser("~/kernel-build/linux-source-7.0.0/fs/nfs"))

with open("nfs4proc.c") as f:
    c = f.read()

# Fix the transport creation loop to set port and correct addrlen
old = """\t\t\t\tstruct xprt_create xprtargs = {
\t\t\t\t\t.ident = XPRT_TRANSPORT_TCP,
\t\t\t\t\t.net = &init_net,
\t\t\t\t\t.dstaddr = (struct sockaddr *)&list->addrs[i],
\t\t\t\t\t.addrlen = sizeof(list->addrs[i]),
\t\t\t\t};"""

new = """\t\t\t\tstruct xprt_create xprtargs = {
\t\t\t\t\t.ident = XPRT_TRANSPORT_TCP,
\t\t\t\t\t.net = &init_net,
\t\t\t\t\t.dstaddr = (struct sockaddr *)&list->addrs[i],
\t\t\t\t\t.addrlen = (list->addrs[i].ss_family == AF_INET6) ? sizeof(struct sockaddr_in6) : sizeof(struct sockaddr_in),
\t\t\t\t};"""

if old in c:
    c = c.replace(old, new)
    # Also set port for IPv6 addresses before each add_xprt call
    c = c.replace(
        "rpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL);",
        """\t\t\t\tif (list->addrs[i].ss_family == AF_INET6) {
\t\t\t\t\t((struct sockaddr_in6 *)&list->addrs[i])->sin6_port = htons(2049);
\t\t\t\t} else {
\t\t\t\t\t((struct sockaddr_in *)&list->addrs[i])->sin_port = htons(2049);
\t\t\t\t}
\t\t\t\trpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL);""")
    with open("nfs4proc.c", "w") as f:
        f.write(c)
    print("Fixed: port + addrlen in transport creation")
else:
    print("Pattern not found in nfs4proc.c")
