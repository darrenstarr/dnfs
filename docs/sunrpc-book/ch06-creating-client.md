# Chapter 6: Creating an RPC Client

## rpc_create Is Your Entry Point

Every RPC conversation starts with `rpc_create()`. This function creates a `struct rpc_clnt` — the handle you'll use for all subsequent RPC calls.

```c
struct rpc_clnt *rpc_create(struct rpc_create_args *args);
```

It returns a pointer to the new client, or an ERR_PTR on failure.

## The rpc_create_args Structure

Before calling `rpc_create()`, you fill in a `struct rpc_create_args`:

```c
struct rpc_create_args {
    struct net           *net;           // Network namespace
    int                  protocol;       // IPPROTO_TCP or IPPROTO_UDP
    struct sockaddr      *address;       // Server address
    size_t               addrsize;       // sizeof(struct sockaddr_in or sockaddr_in6)
    struct sockaddr      *saddress;      // Source address (or NULL)
    size_t               saddrsize;      // sizeof source address
    unsigned long        flags;          // RPC_CLNT_CREATE_* flags
    char                 *servername;    // Server name (for debugging)
    struct rpc_program   *program;       // Program and version info
    rpc_authflavor_t     authflavor;     // RPC_AUTH_NULL, RPC_AUTH_UNIX, etc.
    struct cred          *cred;          // Process credentials (for AUTH_UNIX)
};
```

Let me walk through each field.

### net

The network namespace. Almost always `&init_net` unless you're in a container context.

```c
.net = &init_net,
```

### protocol

TCP or UDP. Always use TCP unless you have a specific reason not to.

```c
.protocol = IPPROTO_TCP,
```

### address and addrsize

The server's IP address and port. For NFS, this is typically port 2049. For our calculator, we'll use port 2049 as well (or any port you choose).

```c
struct sockaddr_in srv_addr = {
    .sin_family = AF_INET,
    .sin_port   = htons(2049),        // or htons(calc_port)
    .sin_addr   = { .saddr = in_aton("10.0.0.1") },
};

.address  = (struct sockaddr *)&srv_addr,
.addrsize = sizeof(srv_addr),
```

### saddress and saddrsize

The source address to bind to (the local network interface). Set to NULL to let the kernel pick. Set it if you need to use a specific NIC.

```c
// Bind to a specific local IP (for multipath)
struct sockaddr_in local_addr = {
    .sin_family = AF_INET,
    .sin_addr   = { .saddr = in_aton("192.168.1.1") },
};

.saddress = (struct sockaddr *)&local_addr,
.saddrsize = sizeof(local_addr),

// Or let the routing table decide:
// .saddress = NULL,
// .saddrsize = 0,
```

### flags

A bitmask controlling client behavior:

| Flag | Meaning |
|------|---------|
| `RPC_CLNT_CREATE_INTR` | Make RPCs interruptible by signals |
| `RPC_CLNT_CREATE_NOPRIVPORT` | Don't use a privileged port (<1024) |
| `RPC_CLNT_CREATE_AUTOBIND` | Use the rpcbind to discover server port |
| `RPC_CLNT_CREATE_NO_IDLE_TIMEOUT` | Don't time out idle connections |
| `RPC_CLNT_CREATE_CONNECTED` | Require TCP connection to be established |
| `RPC_CLNT_CREATE_SOFTERR` | Return soft errors on timeout (vs. hard retry) |

For most clients:

```c
.flags = RPC_CLNT_CREATE_NOPRIVPORT,
```

### servername

A human-readable name for the server, used in debugging output. Set it to the hostname or IP string.

```c
.servername = "calc-server",
```

### program — The Key Structure

The `rpc_program` structure tells the RPC layer what program number and version your service uses:

```c
static struct rpc_program calc_program = {
    .name       = "calculator",
    .number     = CALC_PROG,          // 400001
    .nrvers     = 1,
    .version    = &calc_version,      // Array of version structures
};
```

Each version is described by a `struct rpc_version`:

```c
static struct rpc_version calc_version = {
    .number     = 1,                  // CALC_VERS
    .nrprocs    = 5,                  // 4 procedures + NULL (proc 0)
    .procs      = calc_procedures,    // Array of procedure descriptions
};
```

Each procedure is described by a `struct rpc_procinfo`:

```c
static struct rpc_procinfo calc_procedures[] = {
    [0] = {                          // NULL procedure (always exists)
        .p_proc       = 0,
        .p_encode     = NULL,        // No arguments
        .p_decode     = NULL,        // No results
        .p_arglen     = 0,
        .p_replen     = 0,
        .p_statidx    = 0,
        .p_name       = "NULL",
    },
    [1] = {                          // ADD
        .p_proc       = ADD,         // 1
        .p_encode     = (kxdrproc_t)calc_xdr_encode_args,
        .p_decode     = (kxdrproc_t)calc_xdr_decode_result,
        .p_arglen     = CALC_ARG_SIZE,   // Size of encoded args
        .p_replen     = CALC_RES_SIZE,   // Size of encoded result
        .p_statidx    = 0,
        .p_name       = "ADD",
    },
    // ... SUB, MUL, DIV follow the same pattern
};
```

The `p_encode` and `p_decode` fields point to your XDR functions. The RPC layer calls them automatically when sending a CALL and receiving a REPLY.

Note: procedure 0 (NULL) is always required. It's a no-op used for connectivity checks. The client calls it, the server sends back an empty reply. If you get a reply, the server is alive.

### authflavor and cred

The authentication flavour. For our calculator, we'll use AUTH_NONE (no authentication):

```c
.authflavor = RPC_AUTH_NULL,
.cred       = NULL,
```

For AUTH_UNIX (which is what NFS usually uses):

```c
.authflavor = RPC_AUTH_UNIX,
.cred       = current_cred(),  // The kernel credential of the calling process
```

## Putting It Together

Here's the complete rpc_create call for our calculator client:

```c
struct rpc_clnt *calc_create_client(struct sockaddr *server)
{
    struct sockaddr_in *addr = (struct sockaddr_in *)server;
    struct rpc_create_args args = {
        .net        = &init_net,
        .protocol   = IPPROTO_TCP,
        .address    = (struct sockaddr *)addr,
        .addrsize   = sizeof(*addr),
        .saddress   = NULL,
        .saddrsize  = 0,
        .flags      = RPC_CLNT_CREATE_NOPRIVPORT,
        .servername = "calc-server",
        .program    = &calc_program,
        .version    = &calc_version,
        .authflavor = RPC_AUTH_NULL,
        .cred       = NULL,
    };

    return rpc_create(&args);
}
```

Usage:

```c
struct sockaddr_in server;
struct rpc_clnt *clnt;

server.sin_family = AF_INET;
server.sin_port   = htons(2049);
inet_aton("10.0.0.1", &server.sin_addr);

clnt = calc_create_client((struct sockaddr *)&server);
if (IS_ERR(clnt)) {
    pr_err("Failed to create RPC client: %ld\n", PTR_ERR(clnt));
    return PTR_ERR(clnt);
}

// Use the client...

rpc_destroy(clnt);
```

## What Happens Inside rpc_create

When you call `rpc_create()`, the kernel:

1. **Allocates** a new `rpc_clnt` structure
2. **Creates a transport** (`rpc_xprt`) with a TCP connection to the server
3. **Sets up the transport switch** with one transport in it
4. **Creates an auth context** based on `authflavor`
5. **Registers** the program/version/procedure table with the client
6. **Returns** the client handle

The TCP connection happens asynchronously by default. The client is usable immediately — the first RPC will wait for the connection if it's not yet established.

## Error Handling

`rpc_create()` returns typical kernel error codes:

| ERR_PTR value | What went wrong |
|--------------|-----------------|
| `-ENOMEM` | Couldn't allocate memory for the client |
| `-EAFNOSUPPORT` | Address family not supported (IPv6 with IPv4-only config) |
| `-EPROTONOSUPPORT` | Protocol not supported |
| `-EINVAL` | Invalid arguments (missing program, bad address, etc.) |

Always check with `IS_ERR()`:

```c
clnt = rpc_create(&args);
if (IS_ERR(clnt)) {
    pr_err("rpc_create failed: %ld\n", PTR_ERR(clnt));
    return PTR_ERR(clnt);
}
```

## Cleaning Up

When you're done with the client:

```c
rpc_destroy(clnt);
```

This closes the TCP connection, releases the auth context, and frees the client structure. After calling this, the client handle is invalid. Any in-flight RPC tasks are cancelled.

## The rpc_program Registration (Server Side)

Note that `rpc_program` appears in both client and server code. For the client, it tells the RPC layer what procedures exist and how to encode/decode their arguments. For the server, it does the same thing but in reverse — it's used to dispatch incoming CALLs to the right handler function.

The structure is shared. You define it once (in a shared header) and use it on both sides.

## Quick Reference

```c
// Create
struct rpc_clnt *clnt = rpc_create(&args);

// Use (covered in chapter 7)
struct rpc_task *task = rpc_run_task(&task_setup);

// Destroy
rpc_destroy(clnt);
```

In the next chapter, we'll make actual RPC calls using `rpc_run_task()`.
