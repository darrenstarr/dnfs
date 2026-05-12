#!/usr/bin/python3
"""ansible module: nfs_multipath_mount — manage NFSv4.1 multipath mounts

Creates one mount per storage IP, each with nconnect connections,
all sharing the same server export.  This achieves the aggregate
throughput by creating separate nfs_clients (bypassing the
session trunking limitation on the OceanStor).
"""

import subprocess
import os
import sys
from ansible.module_utils.basic import AnsibleModule


def run(cmd: list[str], timeout=30) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"


def is_mounted(mount_point: str, server: str) -> bool:
    """Check if mount_point has an active NFS mount from server."""
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == mount_point:
                    if parts[0] == server and parts[2] in ("nfs", "nfs4"):
                        return True
        return False
    except Exception:
        return False


def count_tcp_connections(ip: str) -> int:
    rc, out, _ = run(["ss", "-tnp6", "state", "established", "dst", f"[{ip}]"])
    return out.count("ESTAB")


def mount(server: str, export: str, mount_point: str, options: str) -> dict:
    """Mount an NFS export. Returns result dict."""
    if is_mounted(mount_point, server):
        conns = count_tcp_connections(server.split(":")[0].strip("[]"))
        return {
            "mount_point": mount_point,
            "server": server,
            "changed": False,
            "action": "already_mounted",
            "connections": conns,
        }

    # Ensure mount point exists
    os.makedirs(mount_point, exist_ok=True)

    full_options = f"-o {options}"
    rc, out, err = run([
        "mount", "-t", "nfs4", full_options, server, mount_point
    ], timeout=60)

    if rc == 0 or is_mounted(mount_point, server):
        conns = count_tcp_connections(server.split(":")[0].strip("[]"))
        return {
            "mount_point": mount_point,
            "server": server,
            "changed": True,
            "action": "mounted",
            "connections": conns,
        }

    return {
        "mount_point": mount_point,
        "server": server,
        "changed": False,
        "action": "failed",
        "error": err or out or "unknown mount failure",
    }


def unmount(mount_point: str) -> dict:
    if not os.path.ismount(mount_point):
        return {"mount_point": mount_point, "changed": False, "action": "not_mounted"}

    rc, out, err = run(["umount", "-l", mount_point], timeout=30)
    return {
        "mount_point": mount_point,
        "changed": rc == 0,
        "action": "unmounted" if rc == 0 else "unmount_failed",
        "error": err if rc != 0 else "",
    }


def get_mount_info(mount_point: str) -> dict:
    """Get options from an existing mount."""
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[1] == mount_point:
                    return {
                        "source": parts[0],
                        "fstype": parts[2],
                        "options": parts[3],
                    }
    except Exception:
        pass
    return {}


def main():
    module_args = dict(
        state=dict(type="str", default="mounted", choices=["mounted", "absent"]),
        mount_base=dict(type="str", required=True),
        mounts=dict(type="list", required=True, elements="dict", options=dict(
            server_ip=dict(type="str", required=True),
            export=dict(type="str", required=True),
            options=dict(type="str", required=True),
        )),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    state = module.params["state"]
    mount_base = module.params["mount_base"]
    mounts = module.params["mounts"]

    results = []
    total_connections = 0
    changed = False

    for i, mnt in enumerate(mounts):
        idx = i + 1
        mount_point = f"{mount_base}{idx}"
        server = f"[{mnt['server_ip']}]:{mnt['export']}"

        if state == "mounted":
            r = mount(server, mnt["export"], mount_point, mnt["options"])
        else:
            r = unmount(mount_point)

        results.append(r)
        if r["changed"]:
            changed = True
        total_connections += r.get("connections", 0)

    failed = [r for r in results if r.get("action") == "failed"]

    module.exit_json(
        changed=changed,
        mounts_count=len(results),
        total_connections=total_connections,
        results=results,
        failed=failed,
        failed_count=len(failed),
    )


if __name__ == "__main__":
    main()
