#!/usr/bin/python3
"""ansible module: nfs_benchmark — run fio performance tests on NFS mounts

Runs single-stream and aggregate benchmarks, parses fio JSON output,
and reports throughput in GiB/s and Gb/s.
"""

import subprocess
import json
import os
import sys
import time
from ansible.module_utils.basic import AnsibleModule


def run(cmd: list[str], timeout=300) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"


def drop_caches():
    rc, _, _ = run(["sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"])


def create_test_file(path: str, size_gb: int) -> dict:
    """Create a test file of size_gb GB filled with zeros."""
    if os.path.isfile(path):
        actual_size = os.path.getsize(path)
        expected_size = size_gb * 1024 * 1024 * 1024
        if actual_size >= expected_size:
            return {"action": "exists", "path": path, "size_gb": actual_size / (1024**3)}

    count = size_gb * 1024  # 1M blocks
    rc, out, err = run([
        "dd", "if=/dev/zero", f"of={path}",
        "bs=1M", f"count={count}", "conv=fsync"
    ], timeout=size_gb * 30)

    if rc == 0:
        size_gb_actual = os.path.getsize(path) / (1024**3)
        return {"action": "created", "path": path, "size_gb": size_gb_actual}
    return {"action": "failed", "path": path, "error": err or out}


def run_fio(jobs: list[dict], runtime: int, output_json: str = None) -> dict:
    """Run fio with given job definitions. Returns parsed results."""
    cmd = ["fio"]

    for j in jobs:
        cmd.extend([
            f"--name={j['name']}",
            f"--filename={j['filename']}",
            f"--rw={j['rw']}",
            f"--bs={j.get('bs', '1M')}",
            f"--size={j.get('size', '4G')}",
            f"--numjobs={j.get('numjobs', 1)}",
            f"--iodepth={j.get('iodepth', 16)}",
            f"--ioengine={j.get('ioengine', 'libaio')}",
            f"--direct={j.get('direct', 1)}",
        ])
        if j.get("offset"):
            cmd.append(f"--offset={j['offset']}")
        if j.get("end_fsync"):
            cmd.append(f"--end_fsync={j['end_fsync']}")

    cmd.extend([
        f"--runtime={runtime}",
        "--time_based",
        "--group_reporting",
        "--output-format=json",
    ])

    if output_json:
        cmd.append(f"--output={output_json}")

    rc, out, err = run(cmd, timeout=runtime + 60)

    # Parse JSON from stdout
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"error": "fio JSON parse failed", "stdout": out[:500], "stderr": err[:500]}

    return data


def parse_fio_result(data: dict) -> dict:
    """Extract key metrics from fio JSON output."""
    if "error" in data:
        return data

    jobs = data.get("jobs", [])
    total_read_bytes = 0
    total_write_bytes = 0
    total_read_iops = 0
    total_write_iops = 0
    total_runtime_ms = 0

    per_job = []
    for job in jobs:
        r = job.get("read", {})
        w = job.get("write", {})
        jobname = job.get("jobname", "unknown")

        read_bytes = r.get("io_bytes", 0)
        write_bytes = w.get("io_bytes", 0)
        read_iops = r.get("iops", 0)
        write_iops = w.get("iops", 0)

        total_read_bytes += read_bytes
        total_write_bytes += write_bytes
        total_read_iops += read_iops
        total_write_iops += write_iops

        per_job.append({
            "name": jobname,
            "read_mib_per_sec": read_bytes / (1024 * 1024) / (runtime if r.get("runtime", 0) == 0 else max(r.get("runtime", 1) / 1000, 1)),
            "write_mib_per_sec": write_bytes / (1024 * 1024) / (runtime if w.get("runtime", 0) == 0 else max(w.get("runtime", 1) / 1000, 1)),
            "read_iops": round(read_iops),
            "write_iops": round(write_iops),
        })

    runtime_sec = data.get("jobs", [{}])[0].get("read", {}).get("runtime", 0) / 1000
    if runtime_sec == 0:
        runtime_sec = data.get("jobs", [{}])[0].get("write", {}).get("runtime", 0) / 1000
    if runtime_sec == 0:
        runtime_sec = 10  # default

    read_gibs = total_read_bytes / (1024**3) / runtime_sec
    write_gibs = total_write_bytes / (1024**3) / runtime_sec

    return {
        "runtime_sec": round(runtime_sec, 1),
        "total_read_gibs": read_gibs,
        "total_write_gibs": write_gibs,
        "total_read_gbps": read_gibs * 8.59,  # GiB/s → Gb/s
        "total_write_gbps": write_gibs * 8.59,
        "total_read_iops": round(total_read_iops),
        "total_write_iops": round(total_write_iops),
        "read_gibs_pretty": f"{read_gibs:.2f} GiB/s",
        "write_gibs_pretty": f"{write_gibs:.2f} GiB/s",
        "read_gbps_pretty": f"{read_gibs * 8.59:.1f} Gb/s",
        "write_gbps_pretty": f"{write_gibs * 8.59:.1f} Gb/s",
        "per_job": per_job,
    }


def main():
    module_args = dict(
        mount_base=dict(type="str", required=True),
        test_file_name=dict(type="str", default="test20g"),
        test_file_size_gb=dict(type="int", default=20),
        runtime=dict(type="int", default=10),
        num_mounts=dict(type="int", default=8),
        skip_tests=dict(type="list", default=[], elements="str"),
        write_test_file=dict(type="bool", default=True),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    mount_base = module.params["mount_base"]
    test_file_name = module.params["test_file_name"]
    test_file_size_gb = module.params["test_file_size_gb"]
    runtime = module.params["runtime"]
    num_mounts = module.params["num_mounts"]
    skip_tests = set(module.params["skip_tests"])
    write_test_file = module.params["write_test_file"]

    results = {}
    changed = False

    # === Ensure test file exists ===
    if write_test_file and "all" not in skip_tests:
        test_path = f"{mount_base}1/{test_file_name}"
        r = create_test_file(test_path, test_file_size_gb)
        results["test_file"] = r
        if r["action"] == "failed":
            module.exit_json(failed=True, results=results, msg=f"Test file creation failed: {r.get('error')}")
        if r["action"] == "created":
            changed = True

    # === 1. Single-stream read (mount 1) ===
    if "single_read" not in skip_tests:
        drop_caches()
        data = run_fio([
            {
                "name": "single_read",
                "filename": f"{mount_base}1/{test_file_name}",
                "rw": "read",
                "bs": "1M",
                "size": f"{test_file_size_gb // 2}G",
                "numjobs": 1,
                "iodepth": 64,
                "ioengine": "libaio",
                "direct": 1,
            }
        ], runtime)
        results["single_stream_read"] = parse_fio_result(data)

    # === 2. Single-stream write (mount 1) ===
    if "single_write" not in skip_tests:
        drop_caches()
        data = run_fio([
            {
                "name": "single_write",
                "filename": f"{mount_base}1/write_bench",
                "rw": "write",
                "bs": "1M",
                "size": f"{test_file_size_gb // 4}G",
                "numjobs": 1,
                "iodepth": 32,
                "ioengine": "libaio",
                "direct": 0,
                "end_fsync": 1,
            }
        ], runtime)
        results["single_stream_write"] = parse_fio_result(data)

    # === 3. Aggregate read (all mounts, one file, different offsets) ===
    if "aggregate_read" not in skip_tests:
        drop_caches()
        chunk_size = (test_file_size_gb * 1024) // num_mounts  # in MiB
        jobs = []
        for i in range(num_mounts):
            offset = i * chunk_size
            jobs.append({
                "name": f"agg_r{i+1}",
                "filename": f"{mount_base}{i+1}/{test_file_name}",
                "rw": "read",
                "bs": "1M",
                "size": f"{chunk_size}M",
                "offset": f"{offset}M",
                "numjobs": 1,
                "iodepth": 16,
                "ioengine": "libaio",
                "direct": 1,
            })
        data = run_fio(jobs, runtime)
        results["aggregate_read"] = parse_fio_result(data)

    # === 4. Aggregate write (all mounts, different files) ===
    if "aggregate_write" not in skip_tests:
        drop_caches()
        jobs = []
        for i in range(num_mounts):
            jobs.append({
                "name": f"agg_w{i+1}",
                "filename": f"{mount_base}{i+1}/write_aggr_{i+1}",
                "rw": "write",
                "bs": "1M",
                "size": f"{test_file_size_gb // 4}G",
                "numjobs": 1,
                "iodepth": 16,
                "ioengine": "libaio",
                "direct": 0,
                "end_fsync": 1,
            })
        data = run_fio(jobs, runtime)
        results["aggregate_write"] = parse_fio_result(data)

    # === 5. NIC throughput check ===
    if "nic_check" not in skip_tests:
        rc, out, _ = run(["cat", "/proc/net/dev"])
        nic_stats = {}
        for line in out.split("\n"):
            for nic in ["storagea.1001", "storageb.1001"]:
                if nic in line:
                    parts = line.split()
                    nic_stats[nic] = {
                        "rx_bytes": int(parts[1]) if len(parts) > 1 else 0,
                        "tx_bytes": int(parts[9]) if len(parts) > 9 else 0,
                    }
        results["nic_stats"] = nic_stats

    # === Summary ===
    summary = {}
    for key, metric, unit in [
        ("single_stream_read", "total_read_gbps", "Gb/s"),
        ("single_stream_write", "total_write_gbps", "Gb/s"),
        ("aggregate_read", "total_read_gbps", "Gb/s"),
        ("aggregate_write", "total_write_gbps", "Gb/s"),
    ]:
        if key in results and "error" not in results[key]:
            summary[key] = f"{results[key].get(metric, 0):.1f} {unit}"

    results["summary"] = summary

    # Determine pass/fail thresholds
    thresholds = {
        "single_stream_read": 30.0,   # Gb/s minimum
        "aggregate_read": 120.0,       # Gb/s minimum
    }
    failed_thresholds = []
    for key, minimum in thresholds.items():
        if key in results and "error" not in results[key]:
            val = results[key].get("total_read_gbps", 0)
            if val < minimum:
                failed_thresholds.append(f"{key}: {val:.1f} < {minimum} Gb/s")

    module.exit_json(
        changed=changed,
        results=results,
        summary=summary,
        failed_thresholds=failed_thresholds,
        threshold_ok=len(failed_thresholds) == 0,
    )


if __name__ == "__main__":
    main()
