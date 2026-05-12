#!/usr/bin/env python3
"""
nfs-stress — 20+ minute NFS multipath stress test for Huawei OceanStor

Runs cycling read/write workloads across all 8 mounts, logs throughput
per cycle, and generates a summary. Designed for diskpool03 setup with
8 NFS mounts at /dcache/pool1 through /dcache/pool8.

Usage:
  python3 nfs-stress.py                    # 20-minute default
  python3 nfs-stress.py --duration 60      # 60 minutes
  python3 nfs-stress.py --skip-reads       # write-only
  python3 nfs-stress.py --skip-writes      # read-only
  python3 nfs-stress.py --output /tmp/nfs_stress.csv
"""

import subprocess
import time
import argparse
import sys
import os
import signal
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────

MOUNT_BASE = "/dcache/pool"
NUM_MOUNTS = 8
BLOCK_SIZE = "1M"
RUNTIME_PER_CYCLE = 120  # seconds per read + write phase
IODEPTH = 32
NUMJOBS_SINGLE = 1
NUMJOBS_MULTI = 4

# Test file baseline (uses test20g if it exists, creates one otherwise)
TEST_FILE = "test20g"
TEST_FILE_SIZE_GB = 20

# ── Setup ─────────────────────────────────────────────────────

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"

def drop_caches():
    run(["sudo", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"])

def verify_mounts():
    """Ensure all 8 NFS mounts are active."""
    mounted = 0
    for i in range(1, NUM_MOUNTS + 1):
        mp = f"{MOUNT_BASE}{i}"
        if os.path.ismount(mp):
            mounted += 1
    if mounted < NUM_MOUNTS:
        print(f"{RED}WARNING: Only {mounted}/{NUM_MOUNTS} mounts active — expect them at {MOUNT_BASE}1..{MOUNT_BASE}{NUM_MOUNTS}{RESET}", file=sys.stderr)
    return mounted

def ensure_file(mount_path, filename, size_gb):
    """Ensure a test file exists. Returns True if ready."""
    fp = f"{mount_path}/{filename}"
    sz = size_gb * 1024 * 1024 * 1024
    if os.path.isfile(fp) and os.path.getsize(fp) >= sz:
        return True
    print(f"  Creating {size_gb}GB file at {fp}...")
    count = size_gb * 1024
    rc, out, err = run([
        "sudo", "dd", "if=/dev/zero", f"of={fp}",
        "bs=1M", f"count={count}", "conv=fsync"
    ], timeout=size_gb * 60)
    return rc == 0

def fio_read_single(mount_path, filename, runtime, iodepth=None):
    """Single-stream sequential read."""
    fp = f"{mount_path}/{filename}"
    size = min(TEST_FILE_SIZE_GB // 2, 10)
    cmd = [
        "sudo", "fio",
        "--name=read_single",
        f"--filename={fp}", "--rw=read", f"--bs={BLOCK_SIZE}",
        f"--size={size}G", "--numjobs=1",
        f"--iodepth={iodepth or IODEPTH}",
        "--ioengine=libaio", "--direct=1",
        f"--runtime={runtime}", "--time_based",
        "--group_reporting", "--output-format=json",
    ]
    drop_caches()
    rc, out, err = run(cmd, timeout=runtime + 30)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"error": "parse_failed"}

def fio_read_aggregate(runtime):
    """8-mount aggregate read, single file, different offsets."""
    jobs = []
    chunk_mb = (TEST_FILE_SIZE_GB * 1024) // NUM_MOUNTS
    for i in range(NUM_MOUNTS):
        jobs.append({
            "name": f"agg_r{i+1}",
            "filename": f"{MOUNT_BASE}{i+1}/{TEST_FILE}",
            "rw": "read",
            "bs": BLOCK_SIZE,
            "size": f"{chunk_mb}M",
            "offset": f"{i * chunk_mb}M",
            "numjobs": 1,
            "iodepth": 16,
            "ioengine": "libaio",
            "direct": 1,
        })
    drop_caches()
    return run_fio_generic(jobs, runtime)

def fio_write_multi(runtime):
    """8-mount concurrent writes, different files."""
    jobs = []
    for i in range(NUM_MOUNTS):
        jobs.append({
            "name": f"agg_w{i+1}",
            "filename": f"{MOUNT_BASE}{i+1}/stress_w{i+1}",
            "rw": "write",
            "bs": BLOCK_SIZE,
            "size": "2G",
            "numjobs": 1,
            "iodepth": 16,
            "ioengine": "libaio",
            "direct": 0,
            "end_fsync": 1,
        })
    drop_caches()
    return run_fio_generic(jobs, runtime)

def fio_write_single(mount_path, runtime):
    """Single-stream sequential write."""
    fp = f"{mount_path}/stress_single_write"
    jobs = [{
        "name": "write_single",
        "filename": fp,
        "rw": "write",
        "bs": BLOCK_SIZE,
        "size": "4G",
        "numjobs": 1,
        "iodepth": IODEPTH,
        "ioengine": "libaio",
        "direct": 0,
        "end_fsync": 1,
    }]
    drop_caches()
    return run_fio_generic(jobs, runtime)

def run_fio_generic(jobs, runtime):
    cmd = ["sudo", "fio"]
    for j in jobs:
        cmd.extend([
            f"--name={j['name']}", f"--filename={j['filename']}",
            f"--rw={j['rw']}", f"--bs={j.get('bs', '1M')}",
            f"--size={j.get('size', '4G')}",
            f"--numjobs={j.get('numjobs', 1)}",
            f"--iodepth={j.get('iodepth', 16)}",
            f"--ioengine={j.get('ioengine', 'libaio')}",
            f"--direct={j.get('direct', 1)}",
        ])
        if j.get("offset"):
            cmd.append(f"--offset={j['offset']}")
        if j.get("end_fsync"):
            cmd.append("--end_fsync=1")
    cmd.extend([
        f"--runtime={runtime}", "--time_based",
        "--group_reporting", "--output-format=json",
    ])
    rc, out, err = run(cmd, timeout=runtime + 60)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"error": "parse_failed", "stdout": out[:200]}

def extract_bandwidth(fio_result, mode="read"):
    """Extract total bandwidth in MiB/s from fio JSON result."""
    if "error" in fio_result:
        return 0.0
    try:
        jobs = fio_result.get("jobs", [])
        total_bytes = 0
        total_runtime_s = 0
        for job in jobs:
            data = job.get(mode, {})
            total_bytes += data.get("io_bytes", 0)
            rt = data.get("runtime", 10000) / 1000.0
            if rt > total_runtime_s:
                total_runtime_s = rt
        if total_runtime_s > 0:
            return total_bytes / (1024 * 1024) / total_runtime_s
    except Exception:
        pass
    return 0.0

def check_nic_errors():
    """Quick check for NIC errors or drops."""
    issues = []
    for nic in ["storagea.1001", "storageb.1001"]:
        try:
            with open(f"/sys/class/net/{nic}/statistics/rx_errors") as f:
                rx_err = int(f.read().strip())
            with open(f"/sys/class/net/{nic}/statistics/tx_errors") as f:
                tx_err = int(f.read().strip())
            with open(f"/sys/class/net/{nic}/statistics/rx_dropped") as f:
                rx_drop = int(f.read().strip())
            with open(f"/sys/class/net/{nic}/statistics/tx_dropped") as f:
                tx_drop = int(f.read().strip())
            if rx_err or tx_err or rx_drop or tx_drop:
                issues.append(f"{nic}: rx_err={rx_err} tx_err={tx_err} rx_drop={rx_drop} tx_drop={tx_drop}")
        except Exception:
            pass
    return issues

def format_bw(mibs):
    """Human-readable bandwidth string."""
    if mibs < 1000:
        return f"{mibs:.0f} MiB/s ({mibs * 8.59:.1f} Gb/s)"
    gbs = mibs / 1024  # GiB/s
    return f"{gbs:.2f} GiB/s ({gbs * 8.59:.1f} Gb/s)"

# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NFS multipath stress test")
    parser.add_argument("--duration", type=int, default=20, help="Test duration in minutes (default: 20)")
    parser.add_argument("--skip-reads", action="store_true", help="Skip all read tests")
    parser.add_argument("--skip-writes", action="store_true", help="Skip all write tests")
    parser.add_argument("--output", type=str, default=None, help="CSV output path for results")
    args = parser.parse_args()

    # Swap to sudo if needed
    if os.geteuid() != 0:
        print(f"{YELLOW}This script uses sudo for fio and drop_caches. You may be prompted.{RESET}", file=sys.stderr)

    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=args.duration)

    print(f"{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  NFS STRESS TEST — {args.duration} MINUTES{RESET}")
    print(f"{BOLD}  Start: {start_time.strftime('%H:%M:%S')} — Target end: {end_time.strftime('%H:%M:%S')}{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")
    print()

    # Verify setup
    mounted = verify_mounts()
    if mounted == 0:
        print(f"{RED}FATAL: No NFS mounts found at {MOUNT_BASE}*. Exiting.{RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"Mounts active: {mounted}/{NUM_MOUNTS}")
    print(f"Test file: {MOUNT_BASE}1/{TEST_FILE}")

    # Create test file if needed
    print("\nEnsuring test files exist...")
    paths_ok = True
    for i in range(1, NUM_MOUNTS + 1):
        mp = f"{MOUNT_BASE}{i}"
        if os.path.ismount(mp):
            if not ensure_file(mp, TEST_FILE, TEST_FILE_SIZE_GB):
                print(f"{RED}  FAILED to create {mp}/{TEST_FILE}{RESET}", file=sys.stderr)
                paths_ok = False
    if not paths_ok:
        print(f"{RED}FATAL: Could not create test files. Check disk space and NFS mounts.{RESET}", file=sys.stderr)
        sys.exit(1)
    print("Done.\n")

    # Track baseline NIC errors
    baseline_errors = check_nic_errors()
    if baseline_errors:
        print(f"{YELLOW}PRE-EXISTING NIC ERRORS/DROPS:{RESET}")
        for e in baseline_errors:
            print(f"  {e}")
        print()

    # Results accumulator
    results = []
    csv_file = None
    csv_writer = None
    if args.output:
        csv_file = open(args.output, "w", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["cycle", "test_name", "mib_per_sec", "gbps", "timestamp"])

    cycle = 0
    start_ts = time.time()

    def print_result(label, bw, color=GREEN):
        nonlocal cycle
        ts = datetime.now().strftime("%H:%M:%S")
        gbps = bw * 8.59
        line = f"  [{ts}] {label:30s} {bw:8.0f} MiB/s  ({gbps:6.1f} Gb/s)"
        print(f"{color}{line}{RESET}")
        results.append({"cycle": cycle, "test": label, "bw_mibs": bw, "gbps": gbps, "timestamp": ts})
        if csv_writer:
            csv_writer.writerow([cycle, label, f"{bw:.1f}", f"{gbps:.1f}", ts])

    try:
        while datetime.now() < end_time:
            cycle += 1
            elapsed = time.time() - start_ts
            remaining = (end_time - datetime.now()).total_seconds()
            print(f"{BOLD}{'─'*60}{RESET}")
            print(f"{BOLD}  CYCLE {cycle}  |  Elapsed: {int(elapsed)//60}m{int(elapsed)%60}s  |  Remaining: {int(remaining)//60}m{int(remaining)%60}s{RESET}")
            print(f"{BOLD}{'─'*60}{RESET}")

            # ── SINGLE-STREAM READ ──
            if not args.skip_reads:
                print(f"\n{CYAN}  [Single-stream read — mount1, 1 job, iodepth={IODEPTH}]{RESET}")
                for _ in range(3):
                    result = fio_read_single(f"{MOUNT_BASE}1", TEST_FILE, 30)
                    bw = extract_bandwidth(result, "read")
                    print_result(f"  single_read #{_+1}", bw, GREEN if bw > 3000 else YELLOW)
                    if datetime.now() >= end_time:
                        break

            # ── SINGLE-STREAM WRITE ──
            if not args.skip_writes:
                print(f"\n{CYAN}  [Single-stream write — mount1, 1 job]{RESET}")
                result = fio_write_single(f"{MOUNT_BASE}1", 30)
                bw = extract_bandwidth(result, "write")
                print_result("  single_write", bw, GREEN if bw > 1500 else YELLOW)

            # ── AGGREGATE READ ──
            if not args.skip_reads:
                print(f"\n{CYAN}  [Aggregate read — 8 mounts, single file, striped offsets]{RESET}")
                result = fio_read_aggregate(60)
                bw = extract_bandwidth(result, "read")
                print_result("  aggregate_read", bw, GREEN if bw > 15000 else YELLOW)

            # ── AGGREGATE WRITE ──
            if not args.skip_writes:
                print(f"\n{CYAN}  [Aggregate write — 8 mounts, 8 different files]{RESET}")
                result = fio_write_multi(60)
                bw = extract_bandwidth(result, "write")
                print_result("  aggregate_write", bw, GREEN if bw > 10000 else YELLOW)

            # ── NIC health check ──
            issues = check_nic_errors()
            new_issues = [i for i in issues if i not in baseline_errors]
            if new_issues:
                print(f"\n{RED}  NEW NIC ERRORS/DROPS DETECTED:{RESET}")
                for i in new_issues:
                    print(f"    {i}")

            # Small gap between cycles to let server breathe
            if datetime.now() < end_time:
                time.sleep(5)

    except KeyboardInterrupt:
        print(f"\n{YELLOW}  Interrupted by user.{RESET}")

    except Exception as e:
        print(f"\n{RED}  Error: {e}{RESET}", file=sys.stderr)
        import traceback
        traceback.print_exc()

    finally:
        # ── Summary ──
        elapsed = time.time() - start_ts
        print(f"\n{BOLD}{'═'*60}{RESET}")
        print(f"{BOLD}  STRESS TEST COMPLETE  —  {elapsed/60:.1f} minutes{RESET}")
        print(f"{BOLD}{'═'*60}{RESET}")
        print()

        # Per-test-type averages
        for test_name in ["single_read", "single_write", "aggregate_read", "aggregate_write"]:
            vals = [r["bw_mibs"] for r in results if r["test"].startswith(test_name)]
            if vals:
                avg = sum(vals) / len(vals)
                mn = min(vals)
                mx = max(vals)
                print(f"  {test_name:25s}  avg {avg:8.0f} MiB/s  min {mn:8.0f}  max {mx:8.0f}  ({avg*8.59:6.1f} Gb/s)  n={len(vals)}")

        print()
        print(f"  Cycles completed: {cycle}")
        print(f"  Total duration:   {elapsed/60:.1f} minutes")

        # Final NIC check
        issues = check_nic_errors()
        if issues:
            print(f"\n  Final NIC errors/drops:")
            for i in issues:
                print(f"    {i}")

        if csv_file:
            csv_file.close()
            print(f"\n  Results saved to: {args.output}")

if __name__ == "__main__":
    main()
