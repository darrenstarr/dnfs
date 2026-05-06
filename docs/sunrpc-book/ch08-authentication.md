# Chapter 8: Authentication — Who Are You and Why Should I Care?

## The Two-Part Auth Model

Every RPC carries two auth fields: a **credential** and a **verifier**.

- The credential says: "I claim to be X."
- The verifier says: "Here's proof."

```mermaid
flowchart LR
    subgraph RPC CALL Header
        CRED[Credential: I am UID 0, GID 0]
        VERF[Verifier: empty (trust me)]
        BODY[Arguments...]
    end
```

For AUTH_SYS (Unix auth), the credential is a list of Unix group IDs and the verifier is empty. The server trusts that the client is who it claims to be because it trusts the network. This is like an HTTP request that says `X-User: root` without a password — it works if you trust your network.

For RPCSEC_GSS (Kerberos), the credential is a Kerberos service ticket, and the verifier is a cryptographic checksum. The server validates the ticket, checks the checksum, and only then processes the request. This is like an HTTP request with a signed JWT — the server can verify the identity without trusting the network.

## AUTH_NULL: No Authentication

The simplest flavour. The credential and verifier are both empty. The server accepts any request unconditionally.

```c
.authflavor = RPC_AUTH_NULL,
.cred       = NULL,
```

Use this for:
- Internal services on a trusted network
- Testing
- Protocols where authentication is handled at a higher layer

Our calculator uses AUTH_NULL because there's no reason to authenticate arithmetic.

## AUTH_SYS: Unix Credentials

AUTH_SYS sends the caller's UID, GID, and supplementary groups with every RPC:

```c
.authflavor = RPC_AUTH_UNIX,
.cred       = current_cred(),  // kernel credentials of the calling process
```

The credential encodes:

```xdr
struct authsys_parms {
    unsigned int  stamp;         // Timestamp (for replay prevention)
    string        machinename;   // Client hostname
    unsigned int  uid;           // User ID
    unsigned int  gid;           // Group ID
    unsigned int  gids<>;        // Supplementary group IDs (variable array)
};
```

AUTH_SYS is what NFS uses by default (`sec=sys`). It's simple, fast, and trusted-network-only.

**The security model**: if you can send packets to the server, you can be any user. An attacker who can forge packets can impersonate UID 0 (root). This is why NFS with AUTH_SYS should only be deployed on trusted networks.

For our calculator, if we needed per-user accounting:

```c
// Server-side: extract the caller's identity
struct authsys_parms *caller = rqstp->rq_cred;
pr_info("Request from UID %d\n", caller->uid);

// Client-side (automatic when authflavor = RPC_AUTH_UNIX)
// current_cred() provides the calling process's UID/GID
```

## AUTH_NONE vs AUTH_SYS: When to Use Which

| Criteria | Use AUTH_NULL | Use AUTH_SYS |
|----------|--------------|-------------|
| Need to know caller identity? | No | Yes |
| Trusted network? | Either | Yes |
| Testing only? | Yes | No (overkill) |
| Need group-based access control? | No | Yes |

## The Verifier: Why It's Usually Empty

Every auth flavour can theoretically provide a verifier — additional proof beyond the credential. In practice, verifiers are:

- **AUTH_NULL**: Always empty
- **AUTH_SYS**: Always empty (the protocol defines a verifier based on timestamps, but nobody implements it)
- **RPCSEC_GSS**: Contains the GSS-API token (Kerberos ticket, etc.)

The verifier exists in the protocol for future-proofing. In 30+ years of SunRPC, only RPCSEC_GSS has made meaningful use of it.

## Error Handling

Auth errors come back as RPC-level DENIED replies:

```c
// Server-side auth failure can return:
// AUTH_BADCRED      — Can't parse credential
// AUTH_REJECTEDCRED — Credential is invalid (expired, wrong server, etc.)
// AUTH_BADVERF      — Can't parse verifier
// AUTH_REJECTEDVERF — Verifier doesn't match credential
// AUTH_TOOWEAK      — Auth flavour isn't strong enough for this operation
```

The RPC layer handles `AUTH_REJECTEDCRED` automatically for AUTH_SYS by refreshing credentials (re-reading the process's current UID/GID). For other auth errors, the call fails with `-EACCES`.

## RPCSEC_GSS (What You Should Know But Probably Won't Use)

RPCSEC_GSS wraps the entire RPC body in a GSS-API layer:

- **Authentication** (GSS_SERVICE_NONE): Like AUTH_SYS — identifies the caller but doesn't protect data
- **Integrity** (GSS_SERVICE_INTEGRITY): Adds a cryptographic checksum — detects tampering
- **Privacy** (GSS_SERVICE_PRIVACY): Encrypts the RPC body — prevents eavesdropping

```c
// Setting up GSS auth (simplified — actual setup is more involved)
.authflavor = RPC_AUTH_GSS,
.cred       = gss_cred,  // Acquired via gss_acquire_cred()
```

The kernel's RPCSEC_GSS implementation is in `net/sunrpc/auth_gss/`. It's complex (Kerberos is complex) and rarely needed for custom services. NFS uses it for Kerberos-mounted exports (`sec=krb5`, `sec=krb5i`, `sec=krb5p`).

If you need RPCSEC_GSS for your service, the setup process is:

1. The client acquires a GSS credential (kernel upcall to userspace gssd)
2. The credential contains a Kerberos service ticket for the server
3. Each RPC uses the credential to create a GSS context
4. The server verifies the context and accepts/rejects the RPC

This is well-documented in the kernel source at `Documentation/filesystems/nfs/rpcsec_gss.txt`. But for most custom services, AUTH_NULL or AUTH_SYS is sufficient.

## Authentication in the Calculator

Our calculator uses AUTH_NULL. Here's what that looks like on the wire:

```
CALL:
  XID:          0x12345678
  RPC version:  2
  Program:      400001 (CALC_PROG)
  Version:      1
  Procedure:    1 (ADD)
  Credential:   AUTH_NONE, length 0
  Verifier:     AUTH_NONE, length 0
  Arguments:    00 00 00 03 00 00 00 04 (a=3, b=4)
```

The entire auth overhead is 8 bytes (two flavour+length pairs). For AUTH_SYS, it would be ~40-60 bytes depending on group list length. The wire efficiency difference is why AUTH_NULL is popular for internal services.
