# Chapter 4: NFSv4.1 — Sessions, pNFS, and Trunking

NFSv4.1 (RFC 5661) introduced three architectural extensions that fundamentally changed the protocol's scalability and reliability:

| Feature | Problem Solved |
|---------|---------------|
| **Session model** | No deterministic duplicate reply cache for COMPOUND, no ordered operations |
| **pNFS layouts** | Single-server bottleneck for data throughput |
| **Session trunking** | No standard way to use multiple connections for reliability/throughput |

## 4.1 The Session Model

NFSv4.1 replaces the client-id/lease model with a **session-based** state model. Every client-server pairing creates one or more sessions, each with:

- A **slot table** (ordered array of operation slots)
- A **backchannel** (server-to-client RPCs over the same connection)
- A **reply cache** per slot (deterministic duplicate detection)

```mermaid
flowchart TD
    subgraph Client
        C[nfs_client]
        S[Session]
        S --> SL[Slot 0]
        S --> S1[Slot 1]
        S --> S2[Slot 2]
        S --> SN[Slot N-1]
    end
    subgraph Server
        SV[Server Session]
        SV --> SVL[Slot Table]
        SV --> BC[Backchannel]
        BC -->|CB_RECALL| C
    end
    S <-->|Forechannel RPCs| SV
```

### CREATE_SESSION

After SETCLIENTID, the client creates a session:

```mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: SETCLIENTID + SETCLIENTID_CONFIRM
    S-->>C: clientid
    C->>S: CREATE_SESSION(clientid, slot-count, cb-program)
    S-->>C: sessionid, negotiated slot table
    Note over C,S: Session established
    C->>S: SEQUENCE(sessionid, slot#, seqid)
    C->>S: OPEN, READ, WRITE (with sequence)
    S-->>C: Reply (with slot table + seqid updates)
```

### Slot Table Ordering

The slot table guarantees:

1. **Ordered processing** within a slot — operations in one slot are processed in order
2. **At-most-once semantics** — slot table doubles as an exact duplicate cache
3. **Slot-based flow control** — client can't exceed negotiated slot count

```c
struct nfs4_slot_table {
    struct nfs4_slot *slots;        // array of slots
    int               max_slots;    // negotiated maximum
    unsigned long     used_slots;   // bitmap of in-use slots
    unsigned long     highest_used_slotid;
    spinlock_t        slot_tbl_lock;
};
```

Each slot tracks:

```c
struct nfs4_slot {
    struct nfs4_slot_table *table;
    unsigned int            slot_nr;
    unsigned int            seq_nr;        // sequence number (monotonic)
    u32                     slot_nr;       // 0..max_slots-1
    // cached reply
    struct nfs4_cached_res *cached_reply;
};
```

### Backchannel

NFSv4.1 adds reliable server-to-client RPCs:

- The server uses the **backchannel** (same TCP connection) for operations like CB_RECALL
- No separate listener port needed
- Backchannel RPCs share the session's slot table
- The CB_SEQUENCE operation provides the same ordering guarantees

## 4.2 pNFS — Parallel NFS

pNFS separates the **metadata path** (control) from the **data path** (I/O):

```mermaid
flowchart TD
    subgraph Clients
        C[Client]
    end
    subgraph Metadata
        MDS[Metadata Server]
    end
    subgraph Data Servers
        DS1[Data Server 1]
        DS2[Data Server 2]
        DS3[Data Server N]
    end
    C -->|CONTROL PATH: GETATTR, OPEN, LAYOUTGET| MDS
    MDS -->|LAYOUT layout-type| C
    C -->|DATA PATH: READ, WRITE| DS1
    C -->|DATA PATH: READ, WRITE| DS2
    C -->|DATA PATH: READ, WRITE| DS3
```

### Layout Types

| Layout | Standard | Use Case |
|--------|----------|----------|
| **FILE** (flex_files) | RFC 5661 §13 | File-level striping across DS hosts |
| **BLOCK** | RFC 5661 §14 | Block-based (iSCSI, FC) data access |
| **OBJECT** | RFC 5661 §15 | Object storage devices (OSD) |
| **FLEX_FILES** | RFC 8435 | NFSv3 DS backends, mirrored layouts |

### LAYOUT Operations

```mermaid
sequenceDiagram
    participant C as Client
    participant M as Metadata Server
    C->>M: LAYOUTGET(file, type, count)
    M-->>C: layout (device_id, data_server_list, stripe_pattern)
    Note over C: Client knows data layout
    C->>DS[Data Server]: READ/WRITE (using layout)
    DS-->>C: data
    Note over C: Layout expires or needs return
    C->>M: LAYOUTRETURN(layout)
    M-->>C: OK
```

### Layout Structure

```c
struct pnfs_layout_range {
    u64     offset;         // byte offset
    u64     length;         // byte length
    u32     iomode;         // READ, READ_WRITE
};

struct nfs4_layout {
    struct pnfs_layout_range  range;
    struct nfs4_deviceid_node *deviceid;
    layouttype4               type;
    void                     *layout_private;
};
```

### The Linux pNFS Client Implementation

The Linux client implements pNFS through **layout drivers**:

```mermaid
flowchart TD
    NFSC[NFS Client] -->|LAYOUTGET| MD[Metadata Server]
    NFSC --> PNFS[pnfs.c]
    PNFS --> LDRV[Layout Driver]
    LDRV --> FL[filelayout/filelayout.c]
    LDRV --> BL[flexfilelayout/flexfilelayout.c]
    LDRV --> BKL[blocklayout/blocklayout.c]
    FL --> DS[Data Server READ/WRITE]
```

Key files in `fs/nfs/`:

| File | Purpose |
|------|---------|
| `pnfs.c` | Core pNFS infrastructure (layout management, device discovery) |
| `pnfs.h` | Layout driver interface |
| `pnfs_dev.c` | Device ID to data server mapping |
| `pnfs_nfs.c` | NFS-specific pNFS helpers |
| `filelayout/filelayout.c` | File layout driver |
| `flexfilelayout/flexfilelayout.c` | Flexible files layout driver |
| `blocklayout/blocklayout.c` | Block/volume layout driver |

## 4.3 Session Trunking

Session trunking allows a single NFSv4.1 session to use **multiple TCP connections** between the same client and server:

```mermaid
flowchart LR
    subgraph Client
        C[Client]
        C --> S
    end
    subgraph Session
        S[Session]
        S -->|Conn 1| T1[TCP 10.0.0.1:2049]
        S -->|Conn 2| T2[TCP 10.0.0.2:2049]
        S -->|Conn N| TN[TCP 10.0.0.N:2049]
    end
    subgraph Server
        SRV[Server]
        T1 --> SRV
        T2 --> SRV
        TN --> SRV
    end
```

### Trunking Discovery

A client discovers trunkable connections through one of two methods:

1. **Explicit trunking**: Client tries to bind additional connections to an existing session by calling `CREATE_SESSION` with the same session ID
2. **Implicit trunking**: Server advertises trunkable addresses via `GETATTR(fs_locations)` or the `SECINFO_NO_NAME` operation

### Linux Implementation

The Linux NFSv4.1 client supports session trunking through the `nfs4_xprt_switch_connect()` path in `nfs4client.c`. When multiple source addresses or destination addresses are available, the client attempts to bind additional connections to the session.

```mermaid
flowchart TD
    N4C[nfs4_init_session] --> CST[nfs4_xprt_switch_connect]
    CST -->|Primary addr| CT1[Connect main xprt]
    CST -->|Discovery addr| CT2[Connect discovery xprt]
    CT2 -->|Same sessionid| TRI[Trunking confirmed]
    TRI -->|Add to switch| AS[xprt_switch_add_xprt]
    AS -->|N xprts in session| DONE[Trunked session established]
```

## 4.4 Summary

| Feature | NFSv4.0 | NFSv4.1 |
|---------|---------|---------|
| State model | Lease + client ID | Session + slot table |
| Duplicate cache | Per-connection DRC | Per-slot deterministic cache |
| Callbacks | TCP listener on client | Backchannel on same connection |
| Parallel I/O | None | pNFS layouts |
| Multipath | None | Session trunking |
| Failover | Timeout + reconnect | Trunked connection fallback |

The session trunking mechanism is the foundation for client-side multipath NFS. Chapter 5 explores this in detail and discusses its limitations.
