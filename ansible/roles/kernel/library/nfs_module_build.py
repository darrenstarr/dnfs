#!/usr/bin/python3
"""ansible module: nfs_module_build — build and install patched NFS kernel module

Patches fs/nfs/fs_context.c to increase NFS_MAX_CONNECTIONS from 16 to 32,
then builds and installs nfs.ko and nfsv4.ko using the running kernel's
build infrastructure.
"""

import subprocess
import json
import os
import re
import sys
import shutil
from ansible.module_utils.basic import AnsibleModule


def run(cmd: list[str], cwd=None, timeout=120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"


def file_contains(path: str, pattern: str) -> bool:
    if not os.path.isfile(path):
        return False
    with open(path) as f:
        return pattern in f.read()


def check_module_symbols(module_path: str, symbol: str) -> bool:
    rc, out, _ = run(["nm", module_path])
    return symbol in out


def get_loaded_srcversion() -> str:
    path = "/sys/module/nfs/srcversion"
    if os.path.isfile(path):
        with open(path) as f:
            return f.read().strip()
    return ""


def get_installed_srcversion(module_path: str) -> str:
    rc, out, _ = run(["modinfo", module_path])
    for line in out.split("\n"):
        if line.startswith("srcversion:"):
            return line.split(":")[1].strip()
    return ""


def build_module(build_dir: str, headers_dir: str, nfs_src: str) -> tuple[bool, str]:
    """Build nfs.ko against running kernel headers. Returns (success, error_message)."""

    # Copy Module.symvers from running kernel
    symvers_src = os.path.join(headers_dir, "Module.symvers")
    symvers_dst = os.path.join(build_dir, "Module.symvers")
    if os.path.isfile(symvers_src):
        shutil.copy2(symvers_src, symvers_dst)

    # Run make
    cmd = ["make", "-C", headers_dir, f"M={nfs_src}", "modules"]
    rc, out, err = run(cmd, timeout=300)
    if rc != 0:
        # Extract first error line
        error_lines = [l for l in (out + err).split("\n") if "error:" in l]
        return False, error_lines[0] if error_lines else "build failed"

    return True, ""


def install_module(nfs_src: str, dest_dir: str) -> bool:
    """Copy built modules to updates/ directory."""
    for ko in ["nfs.ko", "nfsv4.ko"]:
        src = os.path.join(nfs_src, ko)
        dst = os.path.join(dest_dir, ko)
        if not os.path.isfile(src):
            return False
        shutil.copy2(src, dst)
    return True


def reload_module() -> tuple[bool, str]:
    """Unload and reload NFS modules."""
    # Unmount any NFS first
    run(["umount", "-a", "-t", "nfs4"])

    # Try to remove modules (may fail if in use — ok)
    run(["modprobe", "-r", "nfsv4"], timeout=10)
    run(["modprobe", "-r", "nfs"], timeout=10)

    # Reload
    rc, out, err = run(["modprobe", "nfs"], timeout=30)
    if rc != 0:
        return False, err or "modprobe failed"

    return True, ""


def patch_nconnect_max(source_file: str, new_max: int) -> bool:
    """Patch NFS_MAX_CONNECTIONS in fs_context.c."""
    if not os.path.isfile(source_file):
        return False
    with open(source_file) as f:
        content = f.read()

    # Match: #define NFS_MAX_CONNECTIONS <number>
    pattern = r'#define\s+NFS_MAX_CONNECTIONS\s+\d+'
    replacement = f'#define NFS_MAX_CONNECTIONS {new_max}'

    new_content = re.sub(pattern, replacement, content)

    if new_content != content:
        with open(source_file, "w") as f:
            f.write(new_content)
        return True
    return False


def main():
    module_args = dict(
        build_dir=dict(type="str", required=True),
        headers_dir=dict(type="str", required=True),
        dest_dir=dict(type="str", required=True),
        nconnect_max=dict(type="int", default=32),
        force_rebuild=dict(type="bool", default=False),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    build_dir = module.params["build_dir"]
    headers_dir = module.params["headers_dir"]
    dest_dir = module.params["dest_dir"]
    nconnect_max = module.params["nconnect_max"]
    force_rebuild = module.params["force_rebuild"]

    nfs_src = os.path.join(build_dir, "fs", "nfs")
    fs_context = os.path.join(nfs_src, "fs_context.c")
    nfs_module = os.path.join(nfs_src, "nfs.ko")
    installed_module = os.path.join(dest_dir, "nfs.ko")

    result = {"changed": False, "steps": []}

    # Step 1: Check if source directory exists
    if not os.path.isdir(nfs_src):
        module.fail_json(msg=f"NFS source directory not found: {nfs_src}")

    # Step 2: Patch NFS_MAX_CONNECTIONS if needed
    if patch_nconnect_max(fs_context, nconnect_max):
        result["changed"] = True
        result["steps"].append(f"patched NFS_MAX_CONNECTIONS to {nconnect_max}")
    else:
        current = "unknown"
        with open(fs_context) as f:
            m = re.search(r'NFS_MAX_CONNECTIONS\s+(\d+)', f.read())
            if m:
                current = m.group(1)
        result["steps"].append(f"NFS_MAX_CONNECTIONS already at {current}")

    # Step 3: Build if needed
    need_build = force_rebuild or not os.path.isfile(nfs_module)
    if not need_build and get_loaded_srcversion() != "":
        # Check if loaded module matches what we'd build
        if get_installed_srcversion(installed_module) != get_loaded_srcversion():
            need_build = True

    if need_build:
        ok, err = build_module(build_dir, headers_dir, nfs_src)
        if not ok:
            module.fail_json(msg=f"Build failed: {err}", steps=result["steps"])
        result["changed"] = True
        result["steps"].append("module built successfully")
    else:
        result["steps"].append("module up to date, skipping build")

    # Step 4: Install
    if need_build or result["changed"]:
        if not install_module(nfs_src, dest_dir):
            module.fail_json(msg="Install failed", steps=result["steps"])
        run(["depmod", "-a"])

    # Step 5: Reload if installed module differs from loaded
    if get_installed_srcversion(installed_module) != get_loaded_srcversion() or force_rebuild:
        ok, err = reload_module()
        if not ok:
            module.fail_json(msg=f"Module reload failed: {err}", steps=result["steps"])
        result["steps"].append("module reloaded")
        result["changed"] = True

    # Final verification
    loaded = get_loaded_srcversion()
    installed = get_installed_srcversion(installed_module)
    result["loaded_srcversion"] = loaded
    result["installed_srcversion"] = installed
    result["nconnect_max"] = nconnect_max
    result["module_loaded"] = loaded != ""

    module.exit_json(**result)


if __name__ == "__main__":
    main()
