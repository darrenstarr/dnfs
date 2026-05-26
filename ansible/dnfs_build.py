#!/usr/bin/env python3
"""One-shot NFS multipath kernel module build script."""
import os, sys, subprocess, shutil

BUILD_DIR = "/home/netadmin/kernel-build/linux-source-7.0.0"
HEADERS = "/lib/modules/7.0.0-15-generic/build"
TARBALL = "/usr/src/linux-source-7.0.0.tar.bz2"
NFS_SRC = os.path.join(BUILD_DIR, "fs/nfs")
MOD_DEST = "/lib/modules/7.0.0-15-generic/updates"

def run(cmd, shell=False):
    print(f"  RUN: {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    if isinstance(cmd, str):
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    else:
        r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  STDERR: {r.stderr[-500:]}")
        return False
    return True

# Step 1: Extract source
print("=== Step 1: Extract kernel source ===")
if not os.path.exists(os.path.join(NFS_SRC, "nfs4proc.c")):
    os.makedirs(BUILD_DIR, exist_ok=True)
    run(f"tar xf {TARBALL} --strip-components=1 -C {BUILD_DIR}", shell=True)
    shutil.copy(f"{HEADERS}/Module.symvers", f"{BUILD_DIR}/Module.symvers")
    shutil.copy("/boot/config-7.0.0-15-generic", f"{BUILD_DIR}/.config")
    # Enable CONFIG_NFS_MULTIPATH
    with open(f"{BUILD_DIR}/.config", "a") as f:
        f.write("\nCONFIG_NFS_MULTIPATH=y\n")

# Step 2: Copy our multipath files
print("=== Step 2: Deploy multipath source ===")
for fn, content in [("nfs_multipath.c", '''#include <linux/kernel.h>
#include <linux/string.h>
#include <linux/slab.h>
#include <linux/errno.h>
#include <linux/sunrpc/addr.h>
#include <linux/mutex.h>
#include "nfs_multipath.h"

#define MAX_OPT_STRLEN 4096

static struct nfs_multipath_addrs *g_addrs;
static struct nfs_multipath_addrs *g_local_addrs;
static DEFINE_MUTEX(g_addrs_lock);

static int parse_addr_list(const char *value, struct nfs_multipath_addrs **dst)
{
	struct nfs_multipath_addrs *list;
	const char *p, *next;
	unsigned int count = 0, max_count;
	int ret;

	if (!value || !*value)
		return -EINVAL;
	if (strlen(value) > MAX_OPT_STRLEN)
		return -E2BIG;

	p = value;
	while (*p) {
		while (*p == '~') p++;
		if (!*p) break;
		count++;
		p = strchr(p, '~');
		if (!p) break;
		p++;
	}
	if (count == 0) return -EINVAL;
	max_count = 32;
	if (count > max_count) return -E2BIG;

	list = kzalloc(sizeof(*list) + (count * sizeof(list->addrs[0])), GFP_KERNEL);
	if (!list) return -ENOMEM;
	list->count = 0; list->max = count;

	p = value;
	while (*p && list->count < count) {
		size_t token_len;
		while (*p == '~') p++;
		if (!*p) break;
		next = strchr(p, '~');
		token_len = next ? next - p : strlen(p);
		if (!rpc_pton(&init_net, p, token_len,
		      (struct sockaddr *)&list->addrs[list->count],
		      sizeof(list->addrs[list->count]))) {
			ret = -EINVAL; goto out_free;
		}
		list->count++;
		p = next ? next + 1 : (p + strlen(p));
	}
	mutex_lock(&g_addrs_lock);
	kfree(*dst); *dst = list;
	mutex_unlock(&g_addrs_lock);
	pr_info("mpath: stored %d addrs\\n", list->count);
	return 0;
out_free:
	kfree(list);
	return ret;
}

int nfs_multipath_parse(void *unused, const char *value) {
	return parse_addr_list(value, &g_addrs);
}
int nfs_multipath_parse_local(void *unused, const char *value) {
	return parse_addr_list(value, &g_local_addrs);
}
static struct nfs_multipath_addrs *get_and_clear(struct nfs_multipath_addrs **p) {
	struct nfs_multipath_addrs *list;
	mutex_lock(&g_addrs_lock);
	list = *p; *p = NULL;
	mutex_unlock(&g_addrs_lock);
	return list;
}
struct nfs_multipath_addrs *nfs_multipath_get_addrs(void) {
	return get_and_clear(&g_addrs);
}
EXPORT_SYMBOL(nfs_multipath_get_addrs);
struct nfs_multipath_addrs *nfs_multipath_get_local_addrs(void) {
	return get_and_clear(&g_local_addrs);
}
EXPORT_SYMBOL(nfs_multipath_get_local_addrs);
void nfs_multipath_free_addrs(struct nfs_multipath_addrs *list) {
	kfree(list);
}
EXPORT_SYMBOL(nfs_multipath_free_addrs);
'''), ("nfs_multipath.h", '''#ifndef _NFS_MULTIPATH_H
#define _NFS_MULTIPATH_H
#include <linux/kernel.h>
#include <linux/socket.h>
struct nfs_multipath_addrs {
	unsigned int count;
	unsigned int max;
	struct sockaddr_storage addrs[];
};
int nfs_multipath_parse(void *unused, const char *value);
int nfs_multipath_parse_local(void *unused, const char *value);
struct nfs_multipath_addrs *nfs_multipath_get_addrs(void);
struct nfs_multipath_addrs *nfs_multipath_get_local_addrs(void);
void nfs_multipath_free_addrs(struct nfs_multipath_addrs *list);
#endif
''')]:
    with open(os.path.join(NFS_SRC, fn), "w") as f:
        f.write(content)

# Step 3: Patch source files
print("=== Step 3: Patch source files ===")
cwd = os.getcwd()
os.chdir(NFS_SRC)

# 3a. Kconfig
with open("Kconfig") as f: c = f.read()
if "CONFIG_NFS_MULTIPATH" not in c:
    c = c.replace("config NFS_V4_1_IMPLEMENTATION_ID_DOMAIN",
        "config NFS_MULTIPATH\n\tbool \"NFS client multipath\"\n\tdepends on NFS_FS\n\tdefault n\n\thelp\n\t  Client-side multipath via remoteaddrs= mount option.\n\nconfig NFS_V4_1_IMPLEMENTATION_ID_DOMAIN")
    open("Kconfig","w").write(c)
    print("  Kconfig: OK")

# 3b. Makefile
with open("Makefile") as f: c = f.read()
if "nfs_multipath.o" not in c:
    lines = c.split('\n')
    for i, l in enumerate(lines):
        if 'super.o \\' in l and 'nfs_multipath' not in ''.join(lines[i:i+3]):
            lines.insert(i+1, '\t\t\t   nfs_multipath.o \\')
            break
    c = '\n'.join(lines)
if "ccflags-y += -DCONFIG_NFS_MULTIPATH" not in c:
    c += "\nccflags-y += -DCONFIG_NFS_MULTIPATH\n"
open("Makefile","w").write(c)
print("  Makefile: OK")

# 3c. fs_context.c
with open("fs_context.c") as f: c = f.read()
if "\tOpt_remoteaddrs," not in c:
    c = c.replace("\tOpt_rdma,", "\tOpt_rdma,\n\tOpt_remoteaddrs,\n\tOpt_localaddrs,\n", 1)
if 'fsparam_string("remoteaddrs"' not in c:
    c = c.replace('fsparam_flag  ("rdma",\t\tOpt_rdma),',
        'fsparam_flag  ("rdma",\t\tOpt_rdma),\n\tfsparam_string("remoteaddrs",\tOpt_remoteaddrs),\n\tfsparam_string("localaddrs",\tOpt_localaddrs),')
if '#include "internal.h"' in c and 'nfs_multipath_parse' not in c:
    c = c.replace('#include "internal.h"',
        '#include "internal.h"\n#if IS_ENABLED(CONFIG_NFS_MULTIPATH)\nextern int nfs_multipath_parse(void *, const char *);\n#endif')
if 'case Opt_remoteaddrs:' not in c:
    c = c.replace('\t\tctx->nfs_server.protocol = ret;\n\t\tbreak;\n\tcase Opt_acl:',
        '\t\tctx->nfs_server.protocol = ret;\n\t\tbreak;\n\tcase Opt_remoteaddrs:\n\t\treturn nfs_multipath_parse(NULL, param->string);\n\tcase Opt_localaddrs:\n\t\treturn 0;\n\tcase Opt_acl:')
open("fs_context.c","w").write(c)
print("  fs_context.c: OK")

# 3d. nfs4proc.c - complete fresh patch with inline declarations
with open("nfs4proc.c") as f: c = f.read()
inline_decl = """
#if IS_ENABLED(CONFIG_NFS_MULTIPATH)
struct nfs_multipath_addrs { unsigned int count; unsigned int max; struct sockaddr_storage addrs[]; };
static struct nfs_multipath_addrs *nfs_multipath_get_addrs(void);
static void nfs_multipath_free_addrs(struct nfs_multipath_addrs *list);
#endif
"""
# Remove any previous patch remnants
c = c.replace(inline_decl, "")
hook = "\n\tif (IS_ENABLED(CONFIG_NFS_MULTIPATH)) {\n\t\tstruct nfs_multipath_addrs *list = nfs_multipath_get_addrs();\n\t\tif (list && list->count > 1) {\n\t\t\tstruct rpc_clnt *clnt = clp->cl_rpcclient;\n\t\t\tint i;\n\t\t\tfor (i = 1; i < list->count; i++) {\n\t\t\t\tstruct xprt_create xprtargs = {\n\t\t\t\t\t.ident = XPRT_TRANSPORT_TCP,\n\t\t\t\t\t.net = &init_net,\n\t\t\t\t\t.dstaddr = (struct sockaddr *)&list->addrs[i],\n\t\t\t\t\t.addrlen = sizeof(list->addrs[i]),\n\t\t\t\t};\n\t\t\t\trpc_clnt_add_xprt(clnt, &xprtargs, NULL, NULL);\n\t\t\t}\n\t\t}\n\t\tnfs_multipath_free_addrs(list);\n\t}"
c = c.replace(hook, "")  # Remove previous hook
# Add inline decl after first NFS include
for anchor in ['#include <linux/nfs_fs_sb.h>', '#include <linux/nfs_fs.h>', '#include <linux/nfs.h>']:
    if anchor in c:
        c = c.replace(anchor, anchor + inline_decl)
        print(f"  nfs4proc.c: inline decl at {anchor}")
        break
# Add hook
c = c.replace('rpc_clnt_probe_trunked_xprts(clp->cl_rpcclient, &rpcdata);',
    'rpc_clnt_probe_trunked_xprts(clp->cl_rpcclient, &rpcdata);' + hook)
open("nfs4proc.c","w").write(c)
print("  nfs4proc.c: OK")

os.chdir(cwd)

# Step 4: Build
print("=== Step 4: Build modules ===")
if not run(f"make -j$(nproc) -C {HEADERS} M={NFS_SRC} modules 2>&1", shell=True):
    print("BUILD FAILED")
    sys.exit(1)

# Step 5: Install
print("=== Step 5: Install ===")
os.makedirs(MOD_DEST, exist_ok=True)
for mod in ["nfs.ko", "nfsv4.ko", "nfsv3.ko"]:
    src = os.path.join(NFS_SRC, mod)
    if os.path.exists(src):
        shutil.copy(src, os.path.join(MOD_DEST, mod))
        print(f"  Installed {mod}")
run("depmod -a", shell=True)

print("\n=== BUILD COMPLETE ===")
print(f"Modules installed to {MOD_DEST}")
print("REBOOT REQUIRED to load new module.")
