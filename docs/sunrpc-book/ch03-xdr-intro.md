# Chapter 3: XDR — The Serialization Layer

## "This Is Like JSON"

When a REST API sends data over HTTP, it serializes it as JSON. When an RPC service sends data, it serializes it as XDR.

```json
// JSON object
{
    "a": 3,
    "b": 4,
    "op": "add"
}
```

```xdr
// XDR equivalent (hex dump)
00 00 00 03    // a = 3 (4 bytes, big-endian)
00 00 00 04    // b = 4 (4 bytes, big-endian)
00 00 00 03    // op = "add" (3 bytes, length-prefixed)
61 64 64 00    // "add" + 1 null padding byte
```

The same data, but XDR is:
- **Smaller**: 20 bytes vs ~35 bytes (no field names, no curly braces, no colons)
- **Fixed-width**: every integer is exactly 4 bytes (or 8 for hyper), no variable-length encoding
- **Harder to read**: you can't just look at the hex dump and tell what it says
- **Easier to parse**: you read N bytes, advance pointer N bytes, repeat

The tradeoff is the same as JSON vs. Protocol Buffers: text is debuggable, binary is efficient. XDR chose efficiency.

## The Four-Byte Religion

XDR is built on a single rule: **everything is aligned to 4 bytes, and every integer is big-endian**.

This means:

- An `int` (32-bit) takes exactly 4 bytes
- A `hyper` (64-bit) takes exactly 8 bytes
- A `string` of 5 bytes takes: 4 (length) + 5 (data) + 3 (padding) = 12 bytes
- A `bool` takes 4 bytes (0 or 1 as a 32-bit integer)
- An `enum` takes 4 bytes

The 4-byte alignment is why XDR wastes space on small values. A boolean is 4 bytes. A single byte is padded to 4 bytes. If you're thinking "that's wasteful," you're right — but it was designed in the 1980s when alignment was critical for CPU performance and memory alignment mattered more than bandwidth.

## The Primitive Types

These are the building blocks. Every XDR type is constructed from these.

### Integer (32-bit)

```c
// C type: int32_t, uint32_t
// Wire format: 4 bytes, big-endian
// Example: 42 → 00 00 00 2A
```

### Hyper (64-bit)

```c
// C type: int64_t, uint64_t
// Wire format: 8 bytes, big-endian
// Example: 42 → 00 00 00 00 00 00 00 2A
```

### Enum

```c
// C type: enum (compiled as int32_t)
// Wire format: same as integer
// Example: ADD = 1 → 00 00 00 01
```

### Bool

```c
// C type: bool_t (int32_t)
// Wire format: 0 = false, 1 = true
// Example: true → 00 00 00 01
```

### String

```c
// C type: char *
// Wire format: 4-byte length + N bytes of data + (0-3) padding bytes
// Example: "add" → 00 00 00 03 | 61 64 64 00
//   where 61='a', 64='d', 64='d', 00=padding
```

### Opaque

```c
// C type: unsigned char *, or any raw bytes
// Wire format: same as string (length + data + padding)
// No string null-terminator — this is binary data
```

### Fixed-Length Array

```c
// C type: type name[SIZE]
// Wire format: SIZE elements, each XDR-encoded, no length prefix
// Example: int32_t ids[3] = {1, 2, 3}
//   → 00 00 00 01 00 00 00 02 00 00 00 03
```

### Variable-Length Array

```c
// C type: struct { int len; type *val; }
// Wire format: 4-byte count + N elements
// Example: ints = {3, 5, 7} → 00 00 00 03 00 00 00 05 00 00 00 07
```

### Union (Discriminated)

```c
// C type: struct with discriminant + union
// Wire format: discriminant (4 bytes) + chosen member
// Think of it as a tagged union in Rust, or a discriminated union in TypeScript
```

## "Wait, Where Are the Strings?"

Unlike JSON, XDR doesn't have a native string type. It has `string` — which is really `opaque` with the convention that the bytes are UTF-8 text. There's no null terminator. There's no encoding marker. It's just bytes.

When you see a string in an NFS packet, it's a length-prefixed byte sequence. The server tells you how many bytes the string is, sends those bytes, and pads to 4. That's it. No null termination, no escape sequences, no character encoding negotiation.

This simplicity is intentional. XDR is designed to be **trivial to encode and decode**. You read a length, you read that many bytes, you advance the pointer. There's nothing to interpret.

## Structs in XDR

XDR doesn't have a struct keyword like JSON's object. Instead, **a struct is just the concatenation of its fields, in order.**

```c
// .x file declaration
struct calc_args {
    int a;
    int b;
};

// Wire format: a (4 bytes) | b (4 bytes) = 8 bytes total
// No field names, no separators, no metadata
```

```json
// Equivalent JSON
{"a": 3, "b": 4}
```

The XDR version is 8 bytes (a=00 00 00 03, b=00 00 00 04). The JSON version is 14 bytes, not counting whitespace. XDR is smaller, but JSON is self-describing — you can look at the JSON and know what fields are there. With XDR, you need the schema to decode.

## The xdr_stream — Your Encoding Cursor

In the Linux kernel, you don't encode XDR by manipulating bytes directly. You use a `struct xdr_stream` — think of it as a cursor over a byte buffer.

```c
struct xdr_stream {
    struct xdr_buf *buf;       // The underlying buffer
    __be32 *p;                 // Current position (always 4-byte aligned)
    struct kvec *iov;          // Current iovec
    int end;                   // Remaining space
};
```

You reserve space, write bytes, and advance the cursor:

```c
// Encode an integer
__be32 *p = xdr_reserve_space(xdr, 4);
*p = cpu_to_be32(42);

// Encode a string
__be32 *p = xdr_reserve_space(xdr, 4 + 3);  // length + data
*p = cpu_to_be32(3);                          // string length
memcpy(p + 1, "add", 3);                      // string data
// xdr_reserve_space already padded to 4-byte boundary
```

Think of `xdr_reserve_space` as "ask the stream for N bytes of space, aligned to 4." The stream gives you a pointer, you fill it in. This is like `malloc` but for a fixed-size buffer that you're filling sequentially.

The decode side is symmetric:

```c
// Decode an integer
__be32 *p = xdr_decode_uint32(xdr, &value);
// value now holds the integer in host byte order

// Decode a string (length + data)
unsigned int len;
__be32 *p = xdr_decode_string_inline(xdr, &len);
// p points to the string data, len is the byte count
```

## The Three xdr_buf Regions

An XDR buffer in the kernel has three regions:

```c
struct xdr_buf {
    struct kvec head[1];   // Header: small, fixed-size data
    struct page **pages;   // Pages: large, page-aligned data
    struct kvec tail[1];   // Tail: any remaining data
};
```

For a typical RPC:
- **head** contains the RPC header (XID, program, version, auth, etc.)
- **pages** contain the bulk data (file read/write data)
- **tail** contains any trailing data

Most of your XDR work involves the head region. The pages region is used by NFS for file data but rarely by custom services.

## XDR Macros and Helpers

The kernel provides macros for common patterns:

| Macro | What It Does |
|-------|-------------|
| `xdr_reserve_space(xdr, n)` | Reserve N bytes (aligned to 4) |
| `xdr_encode_uint32(p, v)` | Write 32-bit integer at p |
| `xdr_decode_uint32(p)` | Read 32-bit integer at p |
| `xdr_encode_opaque(p, data, len)` | Write length-prefixed data |
| `xdr_decode_opaque_inline(xdr, &len)` | Read length-prefixed data |
| `xdr_encode_string(p, s)` | Write a null-terminated string |
| `xdr_decode_string_inline(xdr, &len)` | Read a string (returns pointer) |
| `xdr_skip(xdr, n)` | Advance cursor N bytes (for skipping unknown fields) |
| `xdr_set_posiion(xdr, pos)` | Reset cursor to a saved position |

## What This Means for Your Calculator

Our calculator service needs to encode and decode two things:

**Arguments** (for a CALL):
```c
struct calc_args {
    int32_t a;    // First operand
    int32_t b;    // Second operand
};
// Wire: 8 bytes (a + b)
```

**Results** (for a REPLY):
```c
struct calc_result {
    int32_t result;  // The computed value
};
// Wire: 4 bytes
```

The encoder packs these into XDR, and the decoder unpacks them. The XDR stream handles alignment, endianness, and padding automatically.

In the next chapter, we'll see how rpcgen generates this code automatically from a `.x` file — and why you can't use it directly in the kernel.
