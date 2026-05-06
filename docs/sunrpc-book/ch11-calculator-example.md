# Chapter 11: Building a Calculator — A Complete RPC Service

This chapter brings together everything from the previous chapters into a single, working example. By the end, you'll have a kernel module that implements a four-function calculator as an RPC service.

## The Protocol

The calculator provides four operations: ADD, SUB, MUL, and DIV. Each takes two integers and returns one integer plus an error code.

```
Program:    CALC_PROG  (400001)
Version:    CALC_VERS  (1)

Procedure 1:  ADD(a: int, b: int) → { result: int, error: int }
Procedure 2:  SUB(a: int, b: int) → { result: int, error: int }
Procedure 3:  MUL(a: int, b: int) → { result: int, error: int }
Procedure 4:  DIV(a: int, b: int) → { result: int, error: int }
```

## File Layout

```text
calc/
├── calc_prot.h          — Shared types and procedure numbers
├── calc_xdr.c           — XDR encode/decode functions
├── calc_client.c        — Client module (initiator)
├── calc_server.c        — Server module (responder)
└── Makefile             — Build file
```

## calc_prot.h — The Protocol Header

```c
#ifndef _CALC_PROT_H
#define _CALC_PROT_H

#include <linux/types.h>
#include <linux/sunrpc/xdr.h>

/* Procedure numbers */
#define CALC_PROG    400001
#define CALC_VERS    1
#define CALC_NULL    0
#define CALC_ADD     1
#define CALC_SUB     2
#define CALC_MUL     3
#define CALC_DIV     4

/* Argument and result structures */
struct calc_args {
    int32_t a;
    int32_t b;
};

struct calc_result {
    int32_t result;
    int32_t error;          /* 0 = OK, 1 = div by zero, 2 = overflow */
};

/* XDR encode/decode functions */
int calc_xdr_encode_args(struct xdr_stream *xdr,
                         struct calc_args *args);
int calc_xdr_decode_args(struct xdr_stream *xdr,
                         struct calc_args *args);
int calc_xdr_encode_result(struct xdr_stream *xdr,
                           struct calc_result *res);
int calc_xdr_decode_result(struct xdr_stream *xdr,
                           struct calc_result *res);

#endif
```

## calc_xdr.c — The XDR Code

```c
#include "calc_prot.h"

int calc_xdr_encode_args(struct xdr_stream *xdr,
                         struct calc_args *args)
{
    __be32 *p;

    p = xdr_reserve_space(xdr, 8);
    if (unlikely(!p))
        return -ENOSPC;

    *p++ = cpu_to_be32(args->a);
    *p   = cpu_to_be32(args->b);

    return 0;
}

int calc_xdr_decode_args(struct xdr_stream *xdr,
                         struct calc_args *args)
{
    __be32 *p;

    p = xdr_inline_decode(xdr, 8);
    if (unlikely(!p))
        return -ENOSPC;

    args->a = be32_to_cpu(p[0]);
    args->b = be32_to_cpu(p[1]);

    return 0;
}

int calc_xdr_encode_result(struct xdr_stream *xdr,
                           struct calc_result *res)
{
    __be32 *p;

    p = xdr_reserve_space(xdr, 8);
    if (unlikely(!p))
        return -ENOSPC;

    *p++ = cpu_to_be32(res->result);
    *p   = cpu_to_be32(res->error);

    return 0;
}

int calc_xdr_decode_result(struct xdr_stream *xdr,
                           struct calc_result *res)
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

## calc_client.c — The Client Module

```c
#include <linux/module.h>
#include <linux/sunrpc/clnt.h>
#include <linux/sunrpc/sched.h>
#include "calc_prot.h"

/* Procedure info table — maps procedure numbers to XDR functions */
static struct rpc_procinfo calc_procedures[] = {
    [CALC_NULL] = {
        .p_proc    = 0,
        .p_encode  = NULL,
        .p_decode  = NULL,
        .p_arglen  = 0,
        .p_replen  = 0,
        .p_name    = "NULL",
    },
    [CALC_ADD] = {
        .p_proc    = CALC_ADD,
        .p_encode  = (kxdrproc_t)calc_xdr_encode_args,
        .p_decode  = (kxdrproc_t)calc_xdr_decode_result,
        .p_arglen  = 8,
        .p_replen  = 8,
        .p_name    = "ADD",
    },
    [CALC_SUB] = {
        .p_proc    = CALC_SUB,
        .p_encode  = (kxdrproc_t)calc_xdr_encode_args,
        .p_decode  = (kxdrproc_t)calc_xdr_decode_result,
        .p_arglen  = 8,
        .p_replen  = 8,
        .p_name    = "SUB",
    },
    [CALC_MUL] = {
        .p_proc    = CALC_MUL,
        .p_encode  = (kxdrproc_t)calc_xdr_encode_args,
        .p_decode  = (kxdrproc_t)calc_xdr_decode_result,
        .p_arglen  = 8,
        .p_replen  = 8,
        .p_name    = "MUL",
    },
    [CALC_DIV] = {
        .p_proc    = CALC_DIV,
        .p_encode  = (kxdrproc_t)calc_xdr_encode_args,
        .p_decode  = (kxdrproc_t)calc_xdr_decode_result,
        .p_arglen  = 8,
        .p_replen  = 8,
        .p_name    = "DIV",
    },
};

static struct rpc_version calc_version = {
    .number  = CALC_VERS,
    .nrprocs = ARRAY_SIZE(calc_procedures),
    .procs   = calc_procedures,
};

static struct rpc_program calc_program = {
    .name    = "calculator",
    .number  = CALC_PROG,
    .nrvers  = 1,
    .version = &calc_version,
};

struct rpc_clnt *calc_create_client(struct sockaddr *addr)
{
    struct sockaddr_in *sin = (struct sockaddr_in *)addr;
    struct rpc_create_args args = {
        .net        = &init_net,
        .protocol   = IPPROTO_TCP,
        .address    = (struct sockaddr *)sin,
        .addrsize   = sizeof(*sin),
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

int calc_operate(struct rpc_clnt *clnt, int proc,
                 int a, int b, int *result, int *error)
{
    struct calc_args args = { .a = a, .b = b };
    struct calc_result res;
    struct rpc_message msg = {
        .rpc_proc = &calc_procedures[proc],
        .rpc_argp = &args,
        .rpc_resp = &res,
    };
    int ret;

    ret = rpc_call_sync(clnt, &msg, 0);
    if (ret < 0)
        return ret;

    *result = res.result;
    *error  = res.error;
    return 0;
}

/* Simplified usage — no actual module_init, just the pattern */
int calc_demo(void)
{
    struct sockaddr_in server;
    struct rpc_clnt *clnt;
    int result, error, ret;

    /* Set up server address */
    server.sin_family = AF_INET;
    server.sin_port   = htons(2049);
    inet_aton("10.0.0.1", &server.sin_addr);

    /* Create client */
    clnt = calc_create_client((struct sockaddr *)&server);
    if (IS_ERR(clnt))
        return PTR_ERR(clnt);

    /* Add */
    ret = calc_operate(clnt, CALC_ADD, 3, 4, &result, &error);
    if (ret == 0)
        pr_info("3 + 4 = %d\n", result);

    /* Divide by zero */
    ret = calc_operate(clnt, CALC_DIV, 10, 0, &result, &error);
    if (ret == 0 && error)
        pr_info("Division by zero error (code %d)\n", error);

    rpc_destroy(clnt);
    return 0;
}
```

## calc_server.c — The Server Module

```c
#include <linux/module.h>
#include <linux/sunrpc/svc.h>
#include "calc_prot.h"

/* Handler functions */
static int calc_svc_add(struct svc_rqst *rqstp)
{
    struct calc_args *a = rqstp->rq_argp;
    struct calc_result *r = rqstp->rq_resp;
    r->result = a->a + a->b;
    r->error  = 0;
    return 0;
}

static int calc_svc_sub(struct svc_rqst *rqstp)
{
    struct calc_args *a = rqstp->rq_argp;
    struct calc_result *r = rqstp->rq_resp;
    r->result = a->a - a->b;
    r->error  = 0;
    return 0;
}

static int calc_svc_mul(struct svc_rqst *rqstp)
{
    struct calc_args *a = rqstp->rq_argp;
    struct calc_result *r = rqstp->rq_resp;
    r->result = a->a * a->b;
    r->error  = 0;
    return 0;
}

static int calc_svc_div(struct svc_rqst *rqstp)
{
    struct calc_args *a = rqstp->rq_argp;
    struct calc_result *r = rqstp->rq_resp;

    if (a->b == 0) {
        r->result = 0;
        r->error  = 1;   /* Division by zero */
    } else {
        r->result = a->a / a->b;
        r->error  = 0;
    }
    return 0;
}

/* Procedure table (server side) */
static struct svc_procedure calc_svc_procedures[] = {
    [CALC_NULL] = {
        .pc_func    = NULL,
        .pc_decode  = NULL,
        .pc_encode  = NULL,
        .pc_argsize = 0,
        .pc_ressize = 0,
        .pc_name    = "NULL",
    },
    [CALC_ADD] = {
        .pc_func    = calc_svc_add,
        .pc_decode  = (kxdrproc_t)calc_xdr_decode_args,
        .pc_encode  = (kxdrproc_t)calc_xdr_encode_result,
        .pc_argsize = sizeof(struct calc_args),
        .pc_ressize = sizeof(struct calc_result),
        .pc_name    = "ADD",
    },
    [CALC_SUB] = {
        .pc_func    = calc_svc_sub,
        .pc_decode  = (kxdrproc_t)calc_xdr_decode_args,
        .pc_encode  = (kxdrproc_t)calc_xdr_encode_result,
        .pc_argsize = sizeof(struct calc_args),
        .pc_ressize = sizeof(struct calc_result),
        .pc_name    = "SUB",
    },
    [CALC_MUL] = {
        .pc_func    = calc_svc_mul,
        .pc_decode  = (kxdrproc_t)calc_xdr_decode_args,
        .pc_encode  = (kxdrproc_t)calc_xdr_encode_result,
        .pc_argsize = sizeof(struct calc_args),
        .pc_ressize = sizeof(struct calc_result),
        .pc_name    = "MUL",
    },
    [CALC_DIV] = {
        .pc_func    = calc_svc_div,
        .pc_decode  = (kxdrproc_t)calc_xdr_decode_args,
        .pc_encode  = (kxdrproc_t)calc_xdr_encode_result,
        .pc_argsize = sizeof(struct calc_args),
        .pc_ressize = sizeof(struct calc_result),
        .pc_name    = "DIV",
    },
};

static struct svc_version calc_svc_version = {
    .vs_vers     = CALC_VERS,
    .vs_nproc    = ARRAY_SIZE(calc_svc_procedures),
    .vs_proc     = calc_svc_procedures,
};

static struct svc_program calc_svc_program = {
    .pg_prog   = CALC_PROG,
    .pg_name   = "calculator",
    .pg_class  = "calc",
    .pg_vers   = &calc_svc_version,
    .pg_nvers  = 1,
};

static struct svc_serv *calc_server;

static int __init calc_server_init(void)
{
    calc_server = svc_create(&calc_svc_program, 2, NULL);
    if (IS_ERR(calc_server))
        return PTR_ERR(calc_server);

    svc_bind(calc_server, htons(2049));
    svc_start(calc_server);

    pr_info("Calculator RPC server ready on port 2049\n");
    return 0;
}

static void __exit calc_server_exit(void)
{
    svc_stop(calc_server);
    svc_destroy(calc_server);
    pr_info("Calculator RPC server stopped\n");
}

module_init(calc_server_init);
module_exit(calc_server_exit);
MODULE_LICENSE("Dual BSD/GPL");
```

## Makefile

```makefile
obj-m := calc_client.o calc_server.o calc_xdr.o

calc_client-objs := calc_client_mod.o calc_xdr.o
calc_server-objs := calc_server_mod.o calc_xdr.o

KDIR := /lib/modules/$(shell uname -r)/build

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
```

(Note: calc_client_mod.c and calc_server_mod.c are separate files containing the module_init/exit logic, with the shared code in calc_client.c and calc_server.c as shown above.)

## Testing

```bash
# Load the server module (on machine A)
insmod calc_server.ko
dmesg | tail
# "Calculator RPC server ready on port 2049"

# Load the client module (on machine B)
insmod calc_client.ko
dmesg | tail
# "3 + 4 = 7"
# "Division by zero error (code 1)"
```

The server listens on TCP port 2049. The client connects to that port, sends RPCs, and displays the results. The entire SunRPC stack is in play: XDR encoding, transport management, RPC dispatch, auth handling.

## What You've Learned

By building this calculator, you've used every major SunRPC kernel component:

- **rpc_create**: Created a client handle with an rpc_clnt
- **rpc_call_sync**: Made synchronous RPC calls
- **xdr_stream**: Encoded and decoded protocol data
- **svc_create**: Created a server to handle incoming calls
- **svc_program**: Registered your protocol with the RPC layer

This pattern — define types, encode/decode, create client, make calls — is the same for any RPC service in the kernel. NFS uses it. Lockd uses it. rpcbind uses it. Your custom service uses it.

The calculator is a toy, but the infrastructure is real. If you can build the calculator, you can build any RPC service.
