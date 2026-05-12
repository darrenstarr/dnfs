#!/usr/bin/python3
"""ansible module: ipv6_route — manage IPv6 host routes for NFS multipath

Ensures specific storage IPs are routed through specific NIC interfaces
by adding /128 host routes. On a fresh install, the kernel adds /64 subnet
routes via the lowest-metric interface. This module pins individual IPs
to specific interfaces to split traffic across both 100GbE links.

route_table:
  nic_a:
    device: storagea.1001
    ips:
      - fc07:2::11
      - fc07:2::13
  nic_b:
    device: storageb.1001
    ips:
      - fc07:2::12
      - fc07:2::14
"""

import subprocess
import json
import sys
from ansible.module_utils.basic import AnsibleModule


def run(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "command not found"


def route_exists(ip: str, dev: str) -> bool:
    """Check if a /128 host route exists for ip via dev."""
    rc, out, _ = run(["ip", "-6", "route", "show", f"{ip}/128"])
    if rc != 0:
        return False
    return f"dev {dev}" in out


def get_current_routes() -> list[dict]:
    """Return all current host routes to fc07:2::/64 subnet."""
    rc, out, _ = run(["ip", "-6", "route", "show", "fc07:2::0/64"])
    if rc != 0:
        return []
    routes = []
    for line in out.split("\n"):
        if "/128" in line and "dev" in line:
            parts = line.split()
            ip = parts[0] if parts else ""
            dev = ""
            for i, p in enumerate(parts):
                if p == "dev" and i + 1 < len(parts):
                    dev = parts[i + 1]
            routes.append({"ip": ip, "dev": dev})
    return routes


def add_route(ip: str, dev: str) -> dict:
    """Add a /128 host route. Returns changed=True if newly added."""
    if route_exists(ip, dev):
        return {"ip": ip, "dev": dev, "changed": False, "action": "present"}

    rc, out, err = run(["ip", "-6", "route", "add", f"{ip}/128", "dev", dev])
    if rc == 0:
        return {"ip": ip, "dev": dev, "changed": True, "action": "added"}
    # If "File exists", it's already there (race)
    if "File exists" in err or "File exists" in out:
        return {"ip": ip, "dev": dev, "changed": False, "action": "present"}
    return {"ip": ip, "dev": dev, "changed": False, "action": "failed", "error": err}


def remove_route(ip: str, dev: str) -> dict:
    """Remove a /128 host route."""
    if not route_exists(ip, dev):
        return {"ip": ip, "dev": dev, "changed": False, "action": "absent"}
    rc, out, err = run(["ip", "-6", "route", "del", f"{ip}/128", "dev", dev])
    changed = rc == 0 or "No such process" in err
    return {"ip": ip, "dev": dev, "changed": changed, "action": "removed"}


def ensure_subnet_route(dev: str) -> dict:
    """Ensure fc07:2::/64 has a subnet route via the given device."""
    rc, out, _ = run(["ip", "-6", "route", "show", "fc07:2::/64"])
    has_route = f"dev {dev}" in out
    if has_route:
        return {"dev": dev, "changed": False, "action": "subnet_present"}

    # Add subnet route with metric 400 (preferred)
    rc, out, err = run([
        "ip", "-6", "route", "add", "fc07:2::/64", "dev", dev, "metric", "400"
    ])
    if rc == 0 or "File exists" in err:
        return {"dev": dev, "changed": rc == 0, "action": "subnet_added"}
    return {"dev": dev, "changed": False, "action": "subnet_failed", "error": err}


def ping_check(ip: str, dev: str) -> bool:
    """Verify connectivity to a storage IP via a specific interface."""
    rc, out, _ = run([
        "ping6", "-c", "1", "-W", "2", "-I", dev, ip
    ])
    return rc == 0 and "1 received" in out


def main():
    module_args = dict(
        state=dict(type="str", default="present", choices=["present", "absent"]),
        routes=dict(type="list", required=True, elements="dict", options=dict(
            device=dict(type="str", required=True),
            ips=dict(type="list", required=True, elements="str"),
        )),
        ensure_subnet=dict(type="bool", default=True),
        verify=dict(type="bool", default=True),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    state = module.params["state"]
    routes = module.params["routes"]
    ensure_subnet = module.params["ensure_subnet"]
    verify = module.params["verify"]

    results = []
    changed = False

    if state == "present":
        for entry in routes:
            dev = entry["device"]

            # Ensure subnet route exists
            if ensure_subnet:
                r = ensure_subnet_route(dev)
                results.append(r)
                if r["changed"]:
                    changed = True

            # Add host routes for each IP
            for ip in entry["ips"]:
                r = add_route(ip, dev)
                results.append(r)
                if r["changed"]:
                    changed = True

                # Verify connectivity
                if verify and r["action"] not in ("failed",):
                    ok = ping_check(ip, dev)
                    r["reachable"] = ok

    elif state == "absent":
        for entry in routes:
            dev = entry["device"]
            for ip in entry["ips"]:
                r = remove_route(ip, dev)
                results.append(r)
                if r["changed"]:
                    changed = True

    failed = any(r.get("action") == "failed" for r in results)
    unreachable = [r["ip"] for r in results if not r.get("reachable", True)]

    module.exit_json(
        changed=changed,
        failed=failed,
        results=results,
        unreachable=unreachable,
        current_routes=get_current_routes() if verify else [],
    )


if __name__ == "__main__":
    main()
