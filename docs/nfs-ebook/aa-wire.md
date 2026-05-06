# Appendix: NFS Protocol Quick Reference

This appendix provides reference material that complements the narrative chapters. Use it when you need to look up an operation code, understand an error, or recall the structure of a particular protocol message.

## Part 1: NFSv4 Operations

The NFSv4 protocol defines 56 operations that can appear in a COMPOUND RPC. Each operation has a number, a name, and a "personality" — whether it modifies server state (non-idempotent) or merely queries it (idempotent).

### File and Directory Operations

| Op | Name | Safe to Retry? | What It Does |
|----|------|---------------|--------------|
| 3 | ACCESS | Yes | Check access permissions (read, write, execute) for a filehandle |
| 15 | LOOKUP | Yes | Follow a path component from the current filehandle |
| 16 | LOOKUPP | Yes | Go up one directory level (parent of current filehandle) |
| 24 | READ | Yes | Read bytes from a file at a given offset |
| 38 | WRITE | No | Write bytes to a file — state-changing, must be at-most-once |
| 5 | COMMIT | Yes | Flush previously-written data to stable storage |
| 18 | OPEN | No | Open a file, creating server-side state |
| 4 | CLOSE | No | Close a file, releasing open state |
| 19 | OPEN_CONFIRM | No | Confirm an OPEN (part of the two-phase open protocol) |
| 20 | OPEN_DOWNGRADE | No | Reduce an open's access level (e.g., READ|WRITE → READ) |

### State Management

| Op | Name | What It Does |
|----|------|--------------|
| 12 | LOCK | Acquire a byte-range lock on an open file |
| 14 | LOCKU | Release a byte-range lock |
| 13 | LOCKT | Test whether a byte-range lock exists |
| 8 | DELEGRETURN | Return a delegation (client no longer needs it) |
| 7 | DELEGPURGE | Purge all delegations for a client ID (rarely used) |

### Attribute and Namespace Operations

| Op | Name | Purpose |
|----|------|---------|
| 9 | GETATTR | Retrieve file attributes (size, mtime, permissions, ACLs, etc.) |
| 33 | SETATTR | Modify file attributes |
| 10 | GETFH | Get the current filehandle |
| 21 | PUTFH | Set the current filehandle |
| 23 | PUTROOTFH | Set current filehandle to the server's pseudo-root |
| 22 | PUTPUBFH | Set current filehandle to the public filehandle |
| 30 | RESTOREFH | Restore a previously-saved filehandle |
| 29 | SAVEFH | Save the current filehandle for later restoration |
| 25 | READDIR | Read directory entries |
| 26 | READLINK | Read the target of a symbolic link |
| 6 | CREATE | Create a file |
| 27 | REMOVE | Delete a file or directory |
| 28 | RENAME | Rename a file or directory |
| 11 | LINK | Create a hard link |

### NFSv4.1 Session Operations

| Op | Name | Purpose |
|----|------|---------|
| 42 | EXCHANGE_ID | Exchange identity information with the server |
| 43 | CREATE_SESSION | Create a new session (with slot table) |
| 44 | DESTROY_SESSION | Destroy a session |
| 41 | BIND_CONN_TO_SESSION | Bind a new TCP connection to an existing session |
| 54 | SEQUENCE | Begin a session-based COMPOUND (carries slot info) |
| 53 | SECINFO_NO_NAME | Query security flavours without providing a name |

### Why "Safe to Retry" Matters

If the client sends a RENAME and doesn't receive a reply, can it safely send the RENAME again? The answer depends on the operation:

- **Idempotent operations** (Yes): RENAME that creates the same name twice is safe because the second attempt fails harmlessly (the file was already renamed). READ at the same offset is safe. GETATTR is safe.

- **Non-idempotent operations** (No): OPEN creates state; a second OPEN might create a second open state with a different stateid. LOCK acquires a byte-range lock; a second LOCK might succeed (locks are often reentrant) or might conflict with the first. WRITE writes data; a second WRITE at the same offset writes the same data again — which is safe for data integrity but wastes bandwidth.

The session model (NFSv4.1) makes this distinction less important by providing at-most-once execution guarantees. But the distinction still matters for NFSv3 and NFSv4.0 servers.

## Part 2: NFSv4 Error Codes

When an NFSv4 operation fails, the server returns an error code. Here are the most important ones for understanding multipath behavior:

| Code | Name | Meaning |
|------|------|---------|
| 0 | NFS4_OK | Success. The operation completed as requested. |
| 1 | NFS4ERR_PERM | Permission denied. The caller lacks authority. |
| 2 | NFS4ERR_NOENT | No such file or directory. The specified path doesn't exist. |
| 18 | NFS4ERR_NOTDIR | Not a directory. A directory operation was attempted on a file. |
| 19 | NFS4ERR_ISDIR | Is a directory. A file operation was attempted on a directory. |
| 66 | NFS4ERR_STALE | Stale filehandle. The filehandle refers to a file that no longer exists. |
| 70 | NFS4ERR_BADHANDLE | Bad filehandle. The filehandle is malformed. |
| 72 | NFS4ERR_NOTSUPP | Operation not supported. The server doesn't implement this operation. |
| 10010 | NFS4ERR_BADSTATEID | The stateid is invalid or expired. Client must re-open. |
| 10011 | NFS4ERR_BAD_SEQID | The sequence number doesn't match what the server expected. |
| 10012 | NFS4ERR_BADSESSION | The session ID is unknown or expired. Client must create a new session. |
| 10014 | NFS4ERR_CB_PATH_DOWN | The server can't reach the client's callback address. |
| 10015 | NFS4ERR_CLID_INUSE | The client ID is already held by another client. |
| 10016 | NFS4ERR_CONN_NOT_BOUND_TO_SESSION | The connection isn't bound to a session. Send BIND_CONN_TO_SESSION first. |
| 10018 | NFS4ERR_DELAY | Transient error — the server is busy. Client should retry. |
| 10019 | NFS4ERR_EXPIRED | The client's lease has expired. Must re-establish state. |
| 10021 | NFS4ERR_GRACE | The server is in grace period (after reboot). Reclaim old state before performing new operations. |
| 10037 | NFS4ERR_OP_ILLEGAL | The operation number is not supported by this protocol version. |
| 10050 | NFS4ERR_STALE_CLIENTID | The client ID is unknown or expired. Use SETCLIENTID to create a new one. |
| 10051 | NFS4ERR_STALE_STATEID | The stateid is stale (generation number too old). Re-open to get a fresh one. |

### Errors to Watch for During Multipath Testing

When developing a multipath implementation, these errors are the most likely to appear:

**NFS4ERR_BADSESSION** — If the client binds a new transport to a session that the server has forgotten (e.g., after server reboot), the session ID becomes stale and operations fail with this error. The client must detect this and either re-establish the session or fall back to single-path operation.

**NFS4ERR_CONN_NOT_BOUND_TO_SESSION** — If the client attempts to send session operations on a connection that hasn't been bound, the server rejects them. This is a client bug — we should ensure that new transports go through the BIND_CONN_TO_SESSION protocol before being used for session operations.

**NFS4ERR_GRACE** — If the server reboots and the client hasn't recovered its state, new operations are rejected during the grace period. With multipath, the client might have multiple connections — it needs to recover state on all of them.

**NFS4ERR_DELAY** — A transient error that should trigger a retry, potentially on a different transport. Our multipath dispatch should treat NFS4ERR_DELAY like a timeout: retry on the next transport with no error returned to the application.

## Part 3: The COMPOUND RPC on the Wire

For readers who want to understand exactly what bytes travel across the network, here's a NFSv4.1 READ COMPOUND as it appears on the wire.

### Request (client → server)

```
+--------+--------+--------+--------+
|         Record marker             |
|         0x80000024                | ← Last fragment (MSB=1), 36 bytes follow
+--------+--------+--------+--------+
|            XID (0x12345678)       |
+--------+--------+--------+--------+
|   RPC version (2)  | Program (100003 = NFS)
+--------+--------+--------+--------+
|   Version (4)      |   Procedure 1 (COMPOUND)
+--------+--------+--------+--------+
| Auth flavour (1 = AUTH_SYS)       |
+--------+--------+--------+--------+
|   Length  | Machine name...       |
+--------+--------+--------+--------+
|   UID    |   GID     | Aux GIDs   |
+--------+--------+--------+--------+
| Verifier flavour (0 = AUTH_NONE)   |
+--------+--------+--------+--------+
| Tag length  | "read-request"      |
+--------+--------+--------+--------+
| Minor version (1)  | # operations (3)
+--------+--------+--------+--------+
| Op 1: PUTFH | Filehandle length   |
+--------+--------+--------+--------+
| Filehandle bytes...               |
+--------+--------+--------+--------+
| Op 2: READ  | Stateid (16 bytes)  |
+--------+--------+--------+--------+
| Offset (8 bytes)   | Count (4)    |
+--------+--------+--------+--------+
| Op 3: GETATTR | Bitmap: size, mtime
+--------+--------+--------+--------+
```

### Reply (server → client)

```
+--------+--------+--------+--------+
|         Record marker             |
|         0x80012344                | ← 0x012344 = 74564 bytes follow
+--------+--------+--------+--------+
|            XID (0x12345678)       | ← Same XID as request (matching)
+--------+--------+--------+--------+
| Reply status: accepted            |
+--------+--------+--------+--------+
| Auth verifier (AUTH_NONE, 0 bytes)|
+--------+--------+--------+--------+
| Status: OK        | Tag: "read-request"
+--------+--------+--------+--------+
| # operations (3)                   |
+--------+--------+--------+--------+
| Op 1 status: OK  | (no data)       |
+--------+--------+--------+--------+
| Op 2 status: OK  | eof | data len |
+--------+--------+--------+--------+
| Data (up to 1 MB)                  |
+--------+--------+--------+--------+
| Op 3 status: OK  | Attr bitmap    |
+--------+--------+--------+--------+
| size (8 bytes)   | mtime (8 bytes)|
+--------+--------+--------+--------+
```

The total round trip for this exchange is:

- **Request**: ~200 bytes (varies by filehandle length, auth info, tag)
- **Response**: ~100 KB for a typical 128-KB read (varies by I/O size)
- **Overhead**: ~5% for request + response headers
- **Latency**: 0.1-5 ms, depending on network distance and server load

## Part 4: Key Kernel Structures Reference

For developers working on the NFS client, these are the structures you'll encounter most frequently:

### rpc_clnt (net/sunrpc/clnt.h)

The RPC client handle. One per NFS mount (or more precisely, one per unique server + auth combination).

```
rpc_clnt:
  cl_xprt          → The "main" TCP transport (also in the switch)
  cl_xprtswitch    → The transport switch (all transports + policy)
  cl_auth          → Authentication context
  cl_nodename      → Hostname for debugging
  cl_vers          → Protocol version (2, 3, 4)
  cl_softrtry      → Soft mount vs. hard mount
  cl_nconnect      → Number of connections (from -o nconnect=N)
```

### rpc_xprt_switch (net/sunrpc/xprtmultipath.h)

The transport switch. Manages a list of transports and the iterator that selects among them.

```
rpc_xprt_switch:
  xps_xprt_list    → Linked list of rpc_xprt entries
  xps_nxprts       → Total transports in the switch
  xps_nactive      → Transports in CONNECTED state
  xps_iter_ops → Iterator (→xps_iter_init, →xps_iter_next)
```

### rpc_xprt (include/linux/sunrpc/xprt.h)

A single transport — typically a TCP connection.

```
rpc_xprt:
  addr             → Server address (struct sockaddr_storage)
  srcaddr          → Client source address (for binding)
  xprt_switch      → Link back to the switch's list
  state            → Connection state (connected, connecting, dead)
  slot_table       → Available RPC slots
  send_queue       → Queue of tasks waiting to send
  recv_queue       → Tasks waiting for a reply
  cong             → Congestion window tracking
  max_reqs         → Maximum in-flight requests
```

### rpc_task (include/linux/sunrpc/sched.h)

An individual RPC in flight.

```
rpc_task:
  tk_client        → The rpc_clnt this task belongs to
  tk_rqstp         → The request buffer (XDR-encoded)
  tk_status        → Result status (0 = in progress, >0 = completed)
  tk_flags         → RPC_TASK_SOFT (soft mount), RPC_TASK_DNFS, etc.
  tk_timeout       → How long to wait before retransmitting
  tk_action        → State machine function pointer
```

## Part 5: Linux Source Code Navigation

If you're reading the kernel source to understand multipath, start here:

**Transport switch infrastructure:**
- `net/sunrpc/xprtmultipath.c` — The transport switch itself, plus default and session trunking iterators
- `net/sunrpc/xprt.c` — Transport creation, connection management, send/receive
- `net/sunrpc/clnt.c` — `rpc_clnt` lifecycle, `rpc_run_task()`, task dispatch
- `net/sunrpc/sched.c` — The RPC scheduler, task state machine

**NFS client:**
- `fs/nfs/client.c` — `nfs_client` creation, `nfs_create_rpc_client()`
- `fs/nfs/super.c` — Mount path, superblock operations
- `fs/nfs/fs_context.c` — Option parsing (where `remoteaddrs=` is parsed)
- `fs/nfs/internal.h` — NFS internal structures (where we add multipath option fields)

**NFSv4-specific:**
- `fs/nfs/nfs4proc.c` — NFSv4 COMPOUND operation building
- `fs/nfs/nfs4session.c` — Session slot table management
- `fs/nfs/nfs4state.c` — State management (client ID, opens, locks)
- `fs/nfs/nfs4client.c` — NFSv4 client initialization, session trunking

**pNFS (parallel NFS):**
- `fs/nfs/pnfs.c` — Layout management
- `fs/nfs/pnfs_dev.c` — Device ID → data server mapping
- `fs/nfs/filelayout/filelayout.c` — File layout driver
- `fs/nfs/flexfilelayout/flexfilelayout.c` — Flexible files layout driver
