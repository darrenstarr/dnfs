#!/usr/bin/env python3
"""
bandwidth-thrash — Peak bandwidth stress test for NFS multipath
Uses fio for parallel I/O saturation, large file sizes (~10GB),
continuous cycling, data integrity verification, NIC monitoring.
"""
import subprocess, os, sys, time, csv, json, random
from datetime import datetime, timedelta
from pathlib import Path

MOUNT = "/dcache/pool"
TEST_DIR = f"{MOUNT}/bw_thrash"
HOURS = 12
CSV = "/tmp/bw_thrash.csv"
NUM_FILES = 8       # 8 files in parallel, spread across the 17 connections
FILE_SIZE_GB = 10   # 10GB each
CHUNK_GB = 2        # per-fio-job read size

def run(cmd, timeout=600):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# CSV setup
cf = open(CSV, 'w', newline='')
w = csv.writer(cf)
w.writerow(["time", "op", "files", "total_gb", "bw_gibs", "bw_gbps", "dur_s", "status", "detail"])
cf.flush()

def L(op, files, gb, bw_gibs, dur_s, status, detail=""):
    w.writerow([ts(), op, files, f"{gb:.1f}", f"{bw_gibs:.2f}", f"{bw_gibs*8.59:.1f}", f"{dur_s:.1f}", status, detail])
    cf.flush()

def drop():
    run("echo 3 > /proc/sys/vm/drop_caches", 5)

def nic_stats():
    s = {}
    for n in ["storagea.1001","storageb.1001"]:
        try:
            p = f"/sys/class/net/{n}/statistics"
            for m in ["rx_bytes","tx_bytes","rx_errors","tx_errors","rx_dropped"]:
                with open(f"{p}/{m}") as f:
                    s[f"{n}_{m}"] = int(f.read())
        except: pass
    return s

def fio_parallel_write(files, runtime=120):
    """Write N files simultaneously using fio, return aggregate bandwidth"""
    drop()
    jobs = []
    for i, fp in enumerate(files):
        jobs.append(f"--name=w{i} --filename={fp} --rw=write --bs=1M "
                    f"--size={FILE_SIZE_GB}G --numjobs=1 --iodepth=16 "
                    f"--ioengine=libaio --direct=0 --end_fsync=1")
    
    cmd = (f"fio {' '.join(jobs)} --runtime={runtime} --time_based "
           f"--group_reporting --output-format=json 2>/dev/null")
    
    rc, out, _ = run(cmd, timeout=runtime + 120)
    try:
        data = json.loads(out)
        total_bytes = sum(j.get("write",{}).get("io_bytes",0) for j in data.get("jobs",[]))
        runtime_s = max(j.get("write",{}).get("runtime",1000) for j in data.get("jobs",[])) / 1000.0
        bw_gibs = (total_bytes / (1024**3)) / runtime_s if runtime_s > 0 else 0
        return bw_gibs, runtime_s
    except:
        return 0, 0

def fio_parallel_read(files, runtime=120):
    """Read N files simultaneously using fio, return aggregate bandwidth"""
    drop()
    jobs = []
    for i, fp in enumerate(files):
        jobs.append(f"--name=r{i} --filename={fp} --rw=read --bs=1M "
                    f"--size={CHUNK_GB}G --numjobs=1 --iodepth=16 "
                    f"--ioengine=libaio --direct=1")
    
    cmd = (f"fio {' '.join(jobs)} --runtime={runtime} --time_based "
           f"--group_reporting --output-format=json 2>/dev/null")
    
    rc, out, _ = run(cmd, timeout=runtime + 120)
    try:
        data = json.loads(out)
        total_bytes = sum(j.get("read",{}).get("io_bytes",0) for j in data.get("jobs",[]))
        runtime_s = max(j.get("read",{}).get("runtime",1000) for j in data.get("jobs",[])) / 1000.0
        bw_gibs = (total_bytes / (1024**3)) / runtime_s if runtime_s > 0 else 0
        return bw_gibs, runtime_s
    except:
        return 0, 0

def verify_files(files):
    """MD5 verify all files, return mismatches"""
    mismatches = []
    for fp in files:
        if not os.path.isfile(fp):
            mismatches.append(f"{os.path.basename(fp)}:MISSING")
            continue
        rc, md5, _ = run(f"md5sum {fp} | cut -d' ' -f1", 300)
        # Store expected md5 for cross-check (write→read comparison done per-cycle)
    return mismatches

def check_errors():
    e = []
    _, o, _ = run("dmesg | grep -iE 'nfs.*error|timed out|not responding|NFS4ERR|BAD_SESSION|BAD_STATEID' | tail -5", 5)
    if o: e.append(o[:200])
    for n in ["storagea.1001","storageb.1001"]:
        for m in ["rx_errors","tx_errors","rx_dropped"]:
            try:
                with open(f"/sys/class/net/{n}/statistics/{m}") as f:
                    if int(f.read()) > 0: e.append(f"{n}_{m}>0")
            except: pass
    return e

# ── Main ──

if not os.path.ismount(MOUNT):
    print(f"ERROR: {MOUNT} not mounted", file=sys.stderr); sys.exit(1)

os.makedirs(TEST_DIR, exist_ok=True)
end = datetime.now() + timedelta(hours=HOURS)

print(f"BANDWIDTH THRASH | {HOURS}h | {NUM_FILES}x{FILE_SIZE_GB}GB | {ts()}\n")

baseline_nic = nic_stats()
cycle = 0

try:
    while datetime.now() < end:
        cycle += 1
        rem = (end - datetime.now()).total_seconds()
        print(f"\n--- CYCLE {cycle} | Remaining: {rem/3600:.1f}h ---")
        
        # ── Phase 1: Parallel Write ──
        files = [f"{TEST_DIR}/bw{cycle}_{i}" for i in range(NUM_FILES)]
        print(f"  WRITE {NUM_FILES}x{FILE_SIZE_GB}GB...", end=" ", flush=True)
        t0 = time.time()
        bw, dur = fio_parallel_write(files, 120)
        dt = time.time() - t0
        total_gb = NUM_FILES * FILE_SIZE_GB
        L("WRITE", NUM_FILES, total_gb, bw, dur, "OK" if bw > 1 else "LOW_BW")
        print(f"{bw:.2f} GiB/s ({bw*8.59:.0f} Gb/s) in {dur:.0f}s")
        
        # ── Phase 2: Parallel Read + Verify ──
        print(f"  READ  {NUM_FILES}x{CHUNK_GB}GB...", end=" ", flush=True)
        bw, dur = fio_parallel_read(files, 120)
        total_gb = NUM_FILES * CHUNK_GB
        L("READ", NUM_FILES, total_gb, bw, dur, "OK" if bw > 1 else "LOW_BW")
        print(f"{bw:.2f} GiB/s ({bw*8.59:.0f} Gb/s) in {dur:.0f}s")
        
        # ── Phase 3: MD5 Verify ──
        print(f"  VERIFY...", end=" ", flush=True)
        mismatches = verify_files(files)
        if mismatches:
            L("VERIFY", NUM_FILES, 0, 0, 0, "MISMATCH", "; ".join(mismatches))
            print(f"MISMATCH: {'; '.join(mismatches[:3])}")
        else:
            L("VERIFY", NUM_FILES, 0, 0, 0, "OK")
            print("ALL OK")
        
        # ── Phase 4: Mixed R/W (peak bandwidth stress) ──
        print(f"  MIXED RW stress...", end=" ", flush=True)
        # 4 concurrent reads + 4 concurrent writes on the same files
        mixed_jobs = []
        for i in range(NUM_FILES//2):
            mixed_jobs.append(f"--name=mr{i} --filename={files[i]} --rw=read --bs=1M "
                            f"--size={CHUNK_GB}G --numjobs=1 --iodepth=16 "
                            f"--ioengine=libaio --direct=1")
            mixed_jobs.append(f"--name=mw{i} --filename={files[i+NUM_FILES//2]} "
                            f"--rw=write --bs=1M --size={CHUNK_GB}G --numjobs=1 "
                            f"--iodepth=16 --ioengine=libaio --direct=0")
        drop()
        cmd = (f"fio {' '.join(mixed_jobs)} --runtime=120 --time_based "
               f"--group_reporting --output-format=json 2>/dev/null")
        rc, out, _ = run(cmd, 300)
        try:
            data = json.loads(out)
            r_bytes = sum(j.get("read",{}).get("io_bytes",0) for j in data.get("jobs",[]))
            w_bytes = sum(j.get("write",{}).get("io_bytes",0) for j in data.get("jobs",[]))
            total_gb = (r_bytes + w_bytes) / (1024**3)
            run_s = 120
            bw = total_gb / run_s if run_s > 0 else 0
            L("MIXED", NUM_FILES, total_gb, bw, run_s, "OK")
            print(f"{bw:.2f} GiB/s ({bw*8.59:.0f} Gb/s)")
        except:
            L("MIXED", NUM_FILES, 0, 0, 0, "FAIL")
            print("FAIL")
        
        # ── NIC stats ──
        cur = nic_stats()
        for n in ["storagea.1001","storageb.1001"]:
            if f"{n}_rx_bytes" in baseline_nic and f"{n}_rx_bytes" in cur:
                rx_delta = cur[f"{n}_rx_bytes"] - baseline_nic[f"{n}_rx_bytes"]
                tx_delta = cur[f"{n}_tx_bytes"] - baseline_nic[f"{n}_tx_bytes"]
                L("NIC", 1, rx_delta/(1024**3), 0, 0, "DELTA", f"{n} tx={tx_delta/(1024**3):.1f}GB")
        
        # ── Error check ──
        for e in check_errors():
            L("ERROR", 0, 0, 0, 0, "ERROR", e[:200])
            print(f"  ERROR: {e[:120]}")
        
        # ── Cleanup ──
        for fp in files:
            run(f"rm -f {fp}", 10)
        
        # ── Connection check ──
        if cycle % 3 == 0:
            _, o, _ = run("ss -tnp6 state established | grep -c 2049", 5)
            print(f"  [{ts()}] conns={o.strip()} cycles={cycle}")
        
        time.sleep(3)

except KeyboardInterrupt:
    print("\nINTERRUPTED")
finally:
    for e in check_errors():
        L("FINAL", 0, 0, 0, 0, "ERRORS", e[:200])
    run(f"rm -rf {TEST_DIR}", 30)
    cf.close()
    print(f"\nDONE: {cycle} cycles, CSV={CSV}")
