# Appendix: Quick Reference

## Exported SunRPC Functions

### Client API (net/sunrpc/clnt.h)

| Function | Purpose |
|----------|---------|
| `rpc_create()` | Create an RPC client handle |
| `rpc_destroy()` | Destroy a client handle |
| `rpc_call_sync()` | Make a synchronous RPC call |
| `rpc_run_task()` | Create an async RPC task |
| `rpc_killall_tasks()` | Cancel all in-flight tasks for a client |

### XDR API (include/linux/sunrpc/xdr.h)

| Function | Purpose |
|----------|---------|
| `xdr_reserve_space()` | Reserve space in encode buffer |
| `xdr_inline_decode()` | Get pointer to next N decode bytes |
| `xdr_skip()` | Skip N bytes in decode stream |
| `xdr_set_position()` | Reset stream position |
| `xdr_get_position()` | Get current stream position |
| `xdr_init_encode()` | Initialize stream for encoding |
| `xdr_init_decode()` | Initialize stream for decoding |

### XDR Conversion Macros

| Macro | Purpose |
|-------|---------|
| `cpu_to_be32(x)` | Host byte order → big-endian |
| `be32_to_cpu(x)` | Big-endian → host byte order |
| `cpu_to_be64(x)` | Host byte order → big-endian (64-bit) |
| `be64_to_cpu(x)` | Big-endian → host byte order (64-bit) |

### Server API (include/linux/sunrpc/svc.h)

| Function | Purpose |
|----------|---------|
| `svc_create()` | Create an RPC server |
| `svc_destroy()` | Destroy an RPC server |
| `svc_bind()` | Bind server to a port |
| `svc_start()` | Start server thread pool |

## rpcgen Command Reference

| Command | What It Generates |
|---------|------------------|
| `rpcgen file.x` | All files (.h, _xdr.c, _clnt.c, _svc.c) |
| `rpcgen -a file.x` | All + sample Makefile and templates |
| `rpcgen -h file.x` | Header only |
| `rpcgen -c file.x` | XDR code only |
| `rpcgen -l file.x` | Client stub only |
| `rpcgen -m file.x` | Server stub only |
| `rpcgen -t file.x` | Type definitions only (no RPC stubs) |

## XDR Wire Sizes

| C Type | XDR Size | Notes |
|--------|----------|-------|
| `int32_t` | 4 bytes | Signed 32-bit, big-endian |
| `uint32_t` | 4 bytes | Unsigned 32-bit, big-endian |
| `int64_t` | 8 bytes | Signed 64-bit, big-endian |
| `uint64_t` | 8 bytes | Unsigned 64-bit, big-endian |
| `bool_t` | 4 bytes | 0 or 1 as 32-bit integer |
| `enum` | 4 bytes | Compiled as int32_t |
| `float` | 4 bytes | IEEE 754 single |
| `double` | 8 bytes | IEEE 754 double |
| `char[N]` (fixed) | N (padded to 4) | Fixed-length string |
| `char *` (variable) | 4 + len + pad | Length-prefixed, 0-3 padding |
| `opaque[N]` | N (padded to 4) | Fixed-length binary |
| `opaque` (variable) | 4 + len + pad | Length-prefixed binary |

## RPC Error Values

| Constant | Value | Meaning |
|----------|-------|---------|
| `RPC_SUCCESS` | 0 | Call completed successfully |
| `RPC_TIMEDOUT` | -ETIMEDOUT | No response within timeout |
| `RPC_CANTRECV` | -EIO | Transport receive error |
| `RPC_CANTSEND` | -EIO | Transport send error |
| `RPC_AUTHERROR` | -EACCES | Authentication failure |
| `RPC_PROGNOTREGISTERED` | -EPROTONOSUPPORT | Server doesn't serve this program |
| `RPC_PROGVERSMISMATCH` | -EPROTONOSUPPORT | Server doesn't support this version |
| `RPC_GARBAGEARGS` | -EPROTO | Arguments couldn't be decoded |

## Program Number Ranges

| Range | Allocation |
|-------|-----------|
| 0x00000000 - 0x1fffffff | IANA-defined (well-known services) |
| 0x20000000 - 0x3fffffff | User-defined (registered with IANA) |
| 0x40000000 - 0x5fffffff | Transient (for testing, local use) |
| 0x60000000 - 0xffffffff | Reserved |

For your custom service, use the transient range (0x40000000-0x5fffffff). Our calculator uses 400001.
