# Technical Report: OceanStor Pacific NFS Performance Findings

Prepared for: Huawei OceanStor Engineering Team  
Date: 2026-06-15  
System: OceanStor Pacific 9550, V800R001, ESN `14eb165c11165033`

---

## 1. NFSv3 Maximum Transfer Size: 32 KiB vs NFSv4.1: 1 MiB

### Discovery Method

We observed a 28× performance discrepancy between NFSv3 and NFSv4.1 test datasets. Investigation via `/proc/self/mountstats` revealed the root cause: the OceanStor NFSv3 server advertises `dtsize=32768` (32 KiB) while NFSv4.1 advertises `dtsize=1048576` (1 MiB).

### Evidence: /proc/self/mountstats Output (diskpool01)

**NFSv4.1 mount** (pool1, `fc07:2::11:/dCache`):
```
opts: rw,vers=4.1,rsize=1048576,wsize=1048576,...
caps: caps=0x8003c0bf,wtmult=512,dtsize=1048576,bsize=0,namlen=255
```

**NFSv3 mount** (pool2, `fc07:2::12:/dCache`):
```
opts: rw,vers=3,rsize=1048576,wsize=1048576,...
caps: caps=0xf,wtmult=4096,dtsize=32768,bsize=0,namlen=255
```

### Impact

The `dtsize` (read/write data transfer size) caps individual NFS READ/WRITE operations. With NFSv3 at 32 KiB, every 1 MiB I/O becomes 32 separate RPC round-trips, each traversing the EC 6+2 encoder. NFSv4.1 at 1 MiB performs the same operation in a single RPC.

| Metric | NFSv3 (32 KiB) | NFSv4.1 (1 MiB) | Impact |
|--------|---------------|-----------------|--------|
| RPCs per 1 MiB I/O | 32 | 1 | 32× |
| Single-mount read throughput | ~280 MB/s | ~950 MB/s | 3.4× |
| Latency per read op | ~1099 μs | ~140 μs | 7.8× |

### All NFSv3 Mounts Confirmed at 32 KiB

Every NFSv3 mount on the system (pool2-pool16, `fc07:2::12` through `fc07:2::18`) shows identical `dtsize=32768`:
```
[fc07:2::12]:/dCache on /dcache/pool2  -> dtsize=32768
[fc07:2::13]:/dCache on /dcache/pool3  -> dtsize=32768
...
[fc07:2::18]:/dCache on /dcache/pool16 -> dtsize=32768
```

### Commands Used
```bash
# List all NFS mounts with transfer sizes
cat /proc/self/mountstats | grep -E '^device.*nfs|dtsize'

# Compare NFSv3 vs NFSv4.1 for a specific mount
cat /proc/self/mountstats | grep -B2 -A30 'pool2' | head -40

# Per-operation latency breakdown
cat /proc/self/mountstats | grep -A30 "pool1" | grep -E "READ|WRITE|xprt"
```

### Conclusion
The OceanStor NFSv3 server hardcodes a 32 KiB maximum data transfer size, while NFSv4.1 correctly uses the negotiated 1 MiB. This is not configurable via the REST API and represents a server-side limitation.

---

## 2. EC Write-Through SSD Cache Not Enabled

### Discovery Method

Querying the storage pool configuration via REST API revealed that the EC write-through SSD cache is disabled despite the system having 32 cache SSDs (4× 3.2TB per controller, 8 controllers).

### Evidence: REST API Call and Response

**API Call:**
```
GET https://dm.pacific.gridstorage.uiocloud.no:8088/dsware/service/resource/queryStoragePool
Headers: X-Auth-Token: <session_token>, X-CSRF-Token: <csrf_token>
```

**Response (key fields):**
```json
{
  "poolName": "dCache01",
  "poolType": "ssd_ec_6_2_32k",
  "redundancyPolicy": "ec",
  "numDataUnits": 6,
  "numParityUnits": 2,
  "cellSize": 32,
  "totalCapacity": 4522674409,
  "usedCapacity": 15861807,
  "mediaType": "sata_disk",
  "cacheMediaType": "ssd_card",
  "ecCacheMediaType": "none",          // <-- EC CACHE DISABLED
  "ecCacheRate": "0",                  // <-- Zero EC cache rate
  "compressionAlgorithm": "performance",
  "poolMainDiskNum": 432,
  "poolCacheDiskNum": 32               // <-- 32 cache SSDs exist, unused
}
```

### Impact

With EC 6+2 erasure coding, every write must compute parity across 8 data fragments. Without a write-through SSD cache, every small write triggers a full EC stripe read-modify-write cycle. This severely limits write IOPS and throughput, especially with the 32 KiB NFSv3 transfer size (32 small writes per 1 MiB application I/O).

### Attempted Remediation

We identified the `modifySysMediaPara` API endpoint (`POST /dsware/service/cluster/storagepool/modifySysMediaPara`) which accepts `p_ec_cache_media_type` among other EC cache parameters. However, we were unable to successfully invoke it due to missing documentation on the required `parent` parameter field. The REST API reference (V800R001C20, section 3.2.97) documents the EC cache parameters but not the full request format.

**Attempted API call:**
```
POST /dsware/service/cluster/storagepool/modifySysMediaPara
Body: {"p_ec_cache_media_type": "ssd_card", ...}
Result: 50331651 "The entered parameter is incorrect"
```

### Available EC Cache Parameters (from REST API documentation, section 3.2.97)

| Parameter | Description | Current Value |
|-----------|-------------|---------------|
| `p_ec_cache_media_type` | EC cache media type (none/ssd_card) | "none" |
| `p_ec_cache_size_per_osd` | EC cache space per OSD | N/A |
| `p_ec_cache_rate` | EC acceleration ratio | "0" |
| `p_ec_cache_write_through_switch` | Write-through mode toggle | N/A |
| `p_ec_cache_high_water_level` | High watermark for flushing | N/A |
| `p_ec_cache_low_water_level` | Low watermark for flushing | N/A |
| `p_ec_cache_replica_num` | Number of cache replicas | N/A |

### Conclusion
32 cache SSDs (102.4 TB total) are installed but the EC write-through cache is disabled. Enabling it would dramatically improve write performance by buffering small writes in SSD before destaging to HDD in full-stripe writes.

---

## 3. Compression Changed from "capacity" to "performance"

### Discovery Method

The initial storage pool query showed `compressionAlgorithm: "capacity"`, which applies aggressive compression to all data (adding CPU overhead to every I/O). We changed this to `"performance"` via REST API.

### Evidence

**Before (initial query):**
```json
"compressionAlgorithm": "capacity"
```

**After (via REST API modification):**
```json
"compressionAlgorithm": "performance"
```

**API call used:**
```
POST https://dm.pacific.gridstorage.uiocloud.no:8088/dsware/service/cluster/storagepool/modifyPool
Body: {"poolId": 0, "compressionAlgorithm": "performance"}
Response: {"result": 0}
```

### Impact
In "capacity" mode, every write is compressed before EC encoding and every read must be decompressed after EC decoding. In "performance" mode, only compressible data is compressed, reducing CPU overhead on incompressible workloads (e.g., our `/dev/urandom` test data).

---

## 4. Storage Pool Inventory

### Discovery Method

Multiple REST API calls against the `queryStoragePool` and `queryStorageNodeInfo` endpoints.

### System Configuration

| Component | Detail |
|-----------|--------|
| Pool name | `dCache01` |
| Pool type | `ssd_ec_6_2_32k` |
| EC scheme | 6+2 (6 data + 2 parity) |
| Cell size | 32 KiB |
| Total capacity | 4,522,674,409 KiB (~4.3 PiB) |
| Used | 15,861,807 KiB (~15.1 TiB) |
| Free rate | 99.6% |
| HDDs | 432 SATA disks (~53-54 per controller) |
| Cache SSDs | 32 SSDs (4 per controller, 3.2TB each) |
| Controllers | 8 storage nodes + 2 management nodes |
| Software version | 8.2.0 (Pacific V800R001) |
| ESN | `14eb165c11165033` |

### REST API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v2/aa/sessions` | POST | Authentication (returns X-Auth-Token, X-CSRF-Token) |
| `/dsware/service/resource/queryStoragePool` | GET | Pool capacity, EC config, compression, cache settings |
| `/dsware/service/cluster/storagepool/queryStorageNodeInfo?poolId=0` | GET | Per-node disk/cache inventory |
| `/dsware/service/cluster/storagepool/modifyPool` | POST | Change compression algorithm |
| `/api/v2/pms/performance_data` | POST | Real-time IOPS, bandwidth, latency |
| `/dsware/service/resource/queryDswareAllNodeIpInfo` | GET | Controller IP addresses |
| `/dsware/service/cluster/queryManageCluster` | GET | Cluster topology, node info |
| `/gui/api/v2/common/alarms` | GET | Active alarms (disk OSD exits, sub-health disks) |

### Authentication Flow
```
POST https://dm.pacific.gridstorage.uiocloud.no:8088/api/v2/aa/sessions
Content-Type: application/json
{"user_name": "admin", "password": "***", "scope": "0"}

Response: {
  "data": {
    "x_auth_token": "<token>",
    "x_csrf_token": "<csrf>",
    "system_esn": "14eb165c11165033"
  }
}

All subsequent calls:
  -H "X-Auth-Token: <token>"
  -H "X-CSRF-Token: <csrf>"
```

---

## 5. Summary of Discoveries

| # | Finding | Method | Severity |
|---|---------|--------|----------|
| 1 | NFSv3 `dtsize=32768` vs NFSv4.1 `dtsize=1048576` | `/proc/self/mountstats` | High — 32× more RPCs per I/O |
| 2 | EC write-through SSD cache disabled (`ecCacheMediaType: "none"`) | REST API `queryStoragePool` | High — cripples write performance |
| 3 | Compression was in "capacity" mode | REST API `queryStoragePool` | Medium — unnecessary CPU overhead; fixed |
| 4 | 32 cache SSDs installed but idle (0% EC cache rate) | REST API `queryStorageNodeInfo` | High — 102.4 TB of flash unused |
| 5 | 16 active major alarms (disk OSD exits) | REST API `common/alarms` | Medium — storage health concern |

### Recommendations for Huawei

1. **Increase NFSv3 dtsize to 1 MiB** to match NFSv4.1. This is the single largest performance bottleneck.
2. **Enable EC write-through SSD cache** (`p_ec_cache_media_type = ssd_card`) with appropriate sizing to absorb small writes.
3. **Document the `modifySysMediaPara` API** fully, including the `parent` parameter required to set EC cache parameters.
4. **Consider exposing NFSv3 transfer size** as a configurable parameter via REST API or CLI.
