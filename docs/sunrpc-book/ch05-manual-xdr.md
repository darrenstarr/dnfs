# Chapter 5: Writing XDR by Hand (the Kernel Way)

## Why Manual?

In the kernel, you can't use rpcgen-generated XDR code because it depends on user-space libraries. You write XDR encode/decode functions by hand using `struct xdr_stream`.

It's not as tedious as it sounds. Most protocols have 3-5 types, and each type takes about 10 lines of encode + 10 lines of decode. For our calculator, we have two types (`calc_args` and `calc_result`), each with two integer fields. That's 20 lines of encode and 20 lines of decode. Total: one page of code.

## The Encode Pattern

Every encoder follows the same pattern:

```c
int calc_xdr_encode_args(struct xdr_stream *xdr, struct calc_args *args)
{
    __be32 *p;

    // 1. Reserve space for the arguments
    p = xdr_reserve_space(xdr, 8);  // 2 ints × 4 bytes
    if (unlikely(!p))
        return -ENOSPC;

    // 2. Write fields in order
    *p++ = cpu_to_be32(args->a);
    *p++ = cpu_to_be32(args->b);

    // 3. Done
    return 0;
}
```

Step 1 is always: "reserve space." The `xdr_reserve_space()` function returns a pointer to the next available position in the buffer, or NULL if there's not enough room. You **must** check for NULL and return an error if it happens. The `unlikely()` hint tells the compiler this error path is rare.

Step 2 is always: "write bytes and advance." The `__be32` type is "big-endian 32-bit integer." You set it with `cpu_to_be32()` (CPU order to big-endian) and read it with `be32_to_cpu()`.

Step 3 is always: "return 0." There's no cleanup. The stream tracks its own position; you just write and advance.

## The Decode Pattern

Decoders are symmetric:

```c
int calc_xdr_decode_args(struct xdr_stream *xdr, struct calc_args *args)
{
    __be32 *p;

    // 1. "Reserve" for reading (same function — it's really "ensure available")
    p = xdr_reserve_space(xdr, 8);
    if (unlikely(!p))
        return -ENOSPC;

    // 2. Read fields in order
    args->a = be32_to_cpu(*p++);
    args->b = be32_to_cpu(*p++);

    // 3. Done
    return 0;
}
```

Wait — `xdr_reserve_space()` for decoding? That doesn't sound right. You're not reserving space to write, you're reading.

The trick is that `xdr_reserve_space()` does the same thing regardless of direction: it checks that there's enough remaining data, advances the cursor, and returns a pointer to the current position. For encoding, you write to the pointer. For decoding, you read from it.

The kernel actually has a separate function for decoding:

```c
p = xdr_inline_decode(xdr, 8);
if (unlikely(!p))
    return -ENOSPC;
args->a = be32_to_cpu(p[0]);
args->b = be32_to_cpu(p[1]);
```

`xdr_inline_decode()` is the read equivalent of `xdr_reserve_space()`. Same semantics: returns a pointer to N bytes, or NULL if N bytes aren't available. Use `xdr_inline_decode` for decoding and `xdr_reserve_space` for encoding. They're implemented the same way, but using the right one makes your intentions clear.

## Encoding calc_result

```c
int calc_xdr_encode_result(struct xdr_stream *xdr, struct calc_result *res)
{
    __be32 *p;

    p = xdr_reserve_space(xdr, 8);
    if (unlikely(!p))
        return -ENOSPC;

    *p++ = cpu_to_be32(res->result);
    *p++ = cpu_to_be32(res->error);

    return 0;
}
```

```c
int calc_xdr_decode_result(struct xdr_stream *xdr, struct calc_result *res)
{
    __be32 *p;

    p = xdr_inline_decode(xdr, 8);
    if (unlikely(!p))
        return -ENOSPC;

    res->result = be32_to_cpu(p[0]);
    res->error  = be32_to_cpu(p[1]);

    return 0;
}
```

## Encoding Strings (Common Pattern)

Most custom protocols need to encode strings at some point. The pattern is:

```c
int encode_string(struct xdr_stream *xdr, const char *str)
{
    __be32 *p;
    int len = strlen(str);
    int padded_len = (len + 3) & ~3;  // Round up to 4

    // Length field + padded data
    p = xdr_reserve_space(xdr, 4 + padded_len);
    if (unlikely(!p))
        return -ENOSPC;

    // Write length
    *p++ = cpu_to_be32(len);

    // Write data (with zero-padding)
    memcpy(p, str, len);
    if (padded_len > len)
        memset((char *)p + len, 0, padded_len - len);

    return 0;
}
```

```c
int decode_string(struct xdr_stream *xdr, char *buf, int buflen)
{
    __be32 *p;
    int len;

    // Read length
    p = xdr_inline_decode(xdr, 4);
    if (unlikely(!p))
        return -ENOSPC;
    len = be32_to_cpu(*p);

    if (len >= buflen)
        return -E2BIG;

    // Read string data
    int padded_len = (len + 3) & ~3;
    p = xdr_inline_decode(xdr, padded_len);
    if (unlikely(!p))
        return -ENOSPC;

    memcpy(buf, p, len);
    buf[len] = '\0';  // Null-terminate for C

    return len;
}
```

The string encoding pattern appears in almost every protocol. NFS uses it for path names, export names, auth machine names — anything text-based.

## Encoding Variable-Length Arrays

Arrays are length-prefixed:

```c
int encode_int_array(struct xdr_stream *xdr, int *arr, int count)
{
    __be32 *p;

    // Length field
    p = xdr_reserve_space(xdr, 4);
    if (unlikely(!p))
        return -ENOSPC;
    *p++ = cpu_to_be32(count);

    // Array elements
    p = xdr_reserve_space(xdr, count * 4);
    if (unlikely(!p))
        return -ENOSPC;

    for (int i = 0; i < count; i++)
        *p++ = cpu_to_be32(arr[i]);

    return 0;
}
```

## The "This Is Like JSON" Moment Again

If you've ever written a JSON serializer by hand:

```c
json_append(json, "{\"a\":%d,\"b\":%d}", args->a, args->b);
```

And if you've ever written a JSON parser by hand:

```c
json_parse(json, "a", &args->a);
json_parse(json, "b", &args->b);
```

Then XDR is the same thing, but:

- **No field names** — just values in order
- **No variable-length encoding** — everything is fixed-size
- **No type hints** — you need the schema to decode
- **No allocation** — you write into a pre-allocated buffer

XDR is simpler than JSON because XDR doesn't need to handle arbitrary nesting, dynamic typing, or escaping. It's a fixed-schema binary format. You trade flexibility for speed.

## Where the Calculator's XDR Goes

In our calculator service, the XDR functions live in a file called `calc_xdr.c`:

```c
// calc_xdr.c — XDR encode/decode for the calculator protocol
#include <linux/sunrpc/xdr.h>
#include "calc_prot.h"

int calc_xdr_encode_args(struct xdr_stream *, struct calc_args *);
int calc_xdr_decode_args(struct xdr_stream *, struct calc_args *);
int calc_xdr_encode_result(struct xdr_stream *, struct calc_result *);
int calc_xdr_decode_result(struct xdr_stream *, struct calc_result *);
```

These functions are called by the client-side stubs (when making a CALL) and the server-side dispatch (when handling a CALL). The next chapter shows how the client uses them.
