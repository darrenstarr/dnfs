# SunRPC on Linux: A Kernel Developer's Guide

## Table of Contents

| Chapter | Title | What You'll Learn |
|---------|-------|-------------------|
| 1 | [What Is Remote Procedure Call?](ch01-what-is-rpc.md) | The REST analogy, three-number dispatch, XID matching |
| 2 | [Where SunRPC Lives in the Kernel](ch02-sunrpc-in-kernel.md) | Module layout, key structures, file tour |
| 3 | [XDR — The Serialization Layer](ch03-xdr-intro.md) | JSON analogy, primitive types, xdr_stream |
| 4 | [rpcgen — The Protocol Compiler](ch04-rpcgen.md) | .x files, generated code, flags, why you can't use it in the kernel |
| 5 | [Writing XDR by Hand (Kernel Way)](ch05-manual-xdr.md) | Encode/decode patterns, xdr_inline_decode |
| 6 | [Creating an RPC Client](ch06-creating-client.md) | rpc_create_args, program/version/procedure registration |
| 7 | [Making RPC Calls](ch07-making-calls.md) | rpc_call_sync, rpc_run_task, callbacks |
| 8 | [Authentication](ch08-authentication.md) | AUTH_NONE, AUTH_SYS, RPCSEC_GSS, verifiers |
| 9 | [The Kernel RPC Server](ch09-rpc-server.md) | svc_create, dispatch, handler functions |
| 10 | [Backchannel — When the Server Calls You](ch10-backchannel.md) | Webhook analogy, session-based callbacks |
| 11 | [Building a Calculator — Complete RPC Service](ch11-calculator-example.md) | Full working example: client + server + XDR |
| 12 | [How NFS Uses SunRPC](ch12-how-nfs-uses-sunrpc.md) | Production patterns, COMPOUND RPC, concurrency |

## What This Book Is

A practical guide to writing kernel modules that use the Linux SunRPC layer. Every chapter explains why before what. Modern analogies throughout (REST, JSON, webhooks, JWT). The running example is a four-function calculator implemented as a kernel RPC service.

## What You Need to Know

- How to write a kernel module (init/exit, file operations, module parameters)
- C programming
- Basic networking concepts (TCP, IP addresses, ports)

## Kernel Version

All code references target Linux 7.0.0 (Ubuntu 26.04 LTS). The patterns are the same across recent kernel versions.
