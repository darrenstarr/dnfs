# Chapter 2: Sun RPC — The Plumbing Underneath

If the NFS protocol is the house, Sun RPC is the foundation, the plumbing, and the electrical wiring. You don't see it when everything works — you see the polished rooms (file operations) and the fixtures (mount points). But when something breaks, you discover just how much of the system depends on the RPC layer working correctly.

This chapter is not a tutorial on RPC programming. It's an explanation of the specific mechanisms that NFS depends on — the ones that will matter when we start modifying the kernel's RPC layer to support multipath.

## The RPC Contract

Remote Procedure Call is a simple idea with profound implications. The caller invokes a function as if it were local, but the function executes on a different machine. The RPC layer handles all the messy details: serializing arguments, transmitting them over a network, waiting for a response, deserializing results, and returning them to the caller.

The contract between caller and callee is expressed in three numbers:

- **Program number** — identifies the service (NFS is 100003, portmapper/rpcbind is 100000)
- **Version number** — identifies the protocol version (NFS has versions 2, 3, 4)
- **Procedure number** — identifies the operation (in NFSv3: READ is 6, WRITE is 7)

Every RPC is either a **CALL** — "here are my arguments, give me results" — or a **REPLY** — "here are your results, or here's why I couldn't produce them." The caller assigns a **transaction ID** (xid) to every CALL, and the REPLY echoes the xid so the caller can match responses to requests.

This is important for our purposes because the xid is how the kernel's RPC layer tracks in-flight operations. When we have multiple transports, each with multiple in-flight RPCs, the xid namespace must be managed carefully.

## XDR: The Universal Translator

The NFS protocol doesn't use JSON, Protocol Buffers, or any modern serialization format. It uses **eXternal Data Representation (XDR)**, a format specified in RFC 4506.

XDR has a distinctive personality:

**Big-endian byte order**, always. There's no negotiation, no "native byte order" optimization. Every byte on the wire has a defined position. This is the opposite of what modern systems typically do — they'd rather negotiate byte order once and use native ordering for the rest of the conversation. But XDR predates that thinking, and by the time the industry realized that negotiation was worth doing, NFSv4 was already committed to XDR.

**Four-byte alignment.** Every data element starts at a position that's a multiple of 4 bytes from the beginning of the message. If you send a 1-byte value followed by a 4-byte value, the sender pads the 1-byte value with 3 unused bytes. This wastes bandwidth but makes the encoding and decoding logic simple and fast — you can cast directly from a buffer to a structure.

**Variable-length arrays are length-prefixed.** An array of N elements is sent as a 4-byte length (N) followed by N elements. Strings are sent as a 4-byte byte count followed by the characters, followed by zero-padding to the next 4-byte boundary.

The simplicity of XDR is a design choice: **the protocol should be easy to implement correctly.** Complex serialization formats create subtle bugs. XDR is simple enough that you can implement a correct encoder and decoder in an afternoon. This matters when you're porting NFS to a new operating system — and Sun wanted NFS to run everywhere.

## Authentication: How the Server Knows Who You Are

Every RPC carries two authentication fields: a **credential** (who the caller claims to be) and a **verifier** (proof that the credential is genuine). Different authentication "flavours" use these fields differently.

### AUTH_SYS (Unix Authentication)

The simplest flavour: the credential contains a UID, GID, and supplementary group list. The verifier is empty. There's no proof of identity — the client simply asserts who it is. An attacker who can forge packets can impersonate any user.

AUTH_SYS is still the most widely used NFS authentication mechanism because it's simple and because most NFS deployments trust their network. The Linux kernel's `auth_unix.c` module implements it in about 200 lines of code.

### RPCSEC_GSS (Cryptographic Authentication)

RPCSEC_GSS wraps the RPC body in a Generic Security Services (GSS-API) layer that provides authentication, integrity, or privacy (encryption). The most common mechanism is Kerberos 5.

With RPCSEC_GSS, the credential is a GSS token (typically a Kerberos service ticket), and the verifier is a cryptographic checksum of the RPC body. The server validates the service ticket, uses it to verify the checksum, and only then processes the request.

NFSv4 **requires** RPCSEC_GSS support (the "MUST" in RFC 7530). In practice, `sec=sys` is still widely used because Kerberos infrastructure is complex to deploy. But the requirement means that every NFSv4 implementation — including ours — must have correct GSS-API integration.

### What Authentication Means for Multipath

When we bind multiple transports to a single mount, each transport creates its own TCP connection. Each connection independently negotiates authentication. The server must see the same identity on all connections for them to participate in the same multipath set.

This is straightforward with AUTH_SYS (the UID/GID is the same regardless of which TCP connection carries the RPC). With RPCSEC_GSS, each connection needs its own Kerberos session — and the server must recognize that sessions A, B, and C all belong to the same client principal.

NFSv4.1 session trunking handles this through the `BIND_CONN_TO_SESSION` operation, which explicitly links a new connection to an existing authenticated session. Our client-only multipath approach handles it at the `rpc_clnt` level — all transports under the same client share the same authentication context.

## The Portmapper Dance (NFSv3)

Before NFSv4, finding the NFS server was a two-step process:

1. Ask the portmapper (port 111) what port the NFS server is on
2. Ask the NFS server to perform operations

The portmapper protocol is itself an RPC service, which means the client makes an RPC call to program 100000, procedure 3 (GETPORT), asking "what port is program 100003, version 3, protocol TCP running on?" The portmapper responds with a port number, and the client opens a new connection to that port.

This dance happens for each service: NFS, mountd, NLM, NSM, and status. Each on a different port. Each requiring a separate portmapper lookup. Each creating a firewall configuration nightmare.

NFSv4 eliminated this entirely. Everything goes over port 2049. The server exports are discovered through the NFSv4 protocol itself — `GETATTR(fs_locations)` returns a list of server paths, and `PUTROOTFH` starts a namespace traversal that reveals all available exports.

For our multipath work, the important point is that **NFSv4's single-port model is friendlier to multipath**. With NFSv3, every extra transport would potentially need its own mountd and NLM connections. With NFSv4, one port, one service, one connection model.

## The Linux SunRPC Implementation: The Architecture

The Linux kernel's SunRPC implementation (`net/sunrpc/`) is organized in layers:

**At the top**, the `rpc_clnt` structure represents a connection to a remote RPC service. It holds the server's address, the authentication flavour, and a reference to the transport switch. The NFS client creates one `rpc_clnt` per server mount, and all NFS operations flow through it.

**In the middle**, the `rpc_task` represents a single RPC in flight. It tracks the operation state, manages retransmission, and handles the transition from "request queued" to "reply received." The task scheduler (`sched.c`) manages concurrency — multiple tasks can be in flight simultaneously, up to the slot limit.

**At the bottom**, the `rpc_xprt` represents a transport — almost always a TCP connection. The transport handles the raw send/receive of RPC messages. Multiple transports can be bound to the same `rpc_clnt` through the **transport switch** (`xprt_switch` in `xprtmultipath.c`).

This layering is what makes client-side multipath possible. The NFS client sends operations to the `rpc_clnt`. The `rpc_clnt` delegates to the transport switch. The transport switch maintains a list of transports and selects one for each operation. The selection policy is defined by the `xps_iter_ops` function pointer. Install a new iterator — like a round-robin selector — and the RPCs spread across transports automatically.

## What You Need to Remember

The RPC layer is the foundation. When we add multipath to the NFS client, we're modifying the transport switch's iterator — not the NFS protocol itself, not the authentication layer, not the COMPOUND operation builder. The beauty of the layered design is that multipath is largely an RPC-layer concern.

In the next chapter, we climb up from the foundation to see how NFSv4 uses this RPC layer to manage state. The state model is where NFSv4 differs most dramatically from v3, and understanding it is essential before we can understand how multipath interacts with state management.
