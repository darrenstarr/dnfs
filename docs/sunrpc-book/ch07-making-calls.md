# Chapter 7: Making RPC Calls

## rpc_run_task

You have your `rpc_clnt`. Now you want to make RPC calls. The entry point is `rpc_run_task()`:

```c
struct rpc_task *rpc_run_task(const struct rpc_task_setup *setup);
```

It returns a `struct rpc_task *` that represents the RPC in flight. The task runs asynchronously — you provide callbacks, and the RPC layer calls them when the reply arrives or when an error occurs.

## The rpc_task_setup Structure

```c
struct rpc_task_setup {
    struct rpc_clnt     *rpc_client;    // Your client handle
    const struct rpc_call_ops *callback_ops;  // Your callbacks
    struct rpc_rqst     *rqst;          // Pre-allocated request (or NULL)
    unsigned int        flags;          // RPC_TASK_* flags
    unsigned long       timeout;        // Custom timeout (or 0 for default)
};
```

The most important field is `callback_ops` — a structure of function pointers that the RPC layer calls at each stage of the operation:

```c
struct rpc_call_ops {
    void (*rpc_call_prepare)(struct rpc_task *, void *);  // Encode arguments
    void (*rpc_call_done)(struct rpc_task *, void *);     // Decode results
    void (*rpc_call_release)(void *);                      // Clean up
};
```

These are the three hooks you need:

- **rpc_call_prepare**: Called when the task is ready to send. You encode your arguments into the XDR buffer here.
- **rpc_call_done**: Called when the reply arrives. You decode the results here.
- **rpc_call_release**: Called when the task is completely done. You free any temporary data here.

## The Simplify: rpc_call_sync

If you don't want to deal with async callbacks, there's `rpc_call_sync()`:

```c
int rpc_call_sync(struct rpc_clnt *clnt, struct rpc_message *msg, int flags);
```

This is a synchronous call — it blocks until the reply arrives or the call times out. It's simpler to use, but it blocks the calling thread.

```c
struct rpc_message msg = {
    .rpc_proc = &calc_procedures[ADD],   // Which procedure
    .rpc_argp = &my_args,                 // Pointer to arguments
    .rpc_resp = &my_result,               // Pointer to result buffer
};

int status = rpc_call_sync(clnt, &msg, 0);
if (status == 0) {
    // my_result contains the server's response
}
```

`rpc_call_sync` handles the encoding/decoding automatically — it calls your XDR encoder before sending and your XDR decoder after receiving. It handles retries and timeouts internally.

For most kernel modules, `rpc_call_sync` is the right choice. It's simple, it's synchronous (which matches kernel module expectations), and it handles errors predictably.

## The Async Way: rpc_run_task

If you need to manage multiple in-flight RPCs concurrently (like NFS does), use `rpc_run_task`:

```c
struct calc_data {
    struct calc_args   args;
    struct calc_result result;
    struct completion  done;
};

static void calc_prepare(struct rpc_task *task, void *data)
{
    struct calc_data *cd = data;
    // Encode args into the task's XDR buffer
    calc_xdr_encode_args(task->tk_rqstp->rq_xdr, &cd->args);
}

static void calc_done(struct rpc_task *task, void *data)
{
    struct calc_data *cd = data;
    // Decode results from the reply
    calc_xdr_decode_result(task->tk_rqstp->rq_xdr, &cd->result);
    complete(&cd->done);
}

static void calc_release(void *data)
{
    // Nothing to clean up in this simple case
}

static const struct rpc_call_ops calc_ops = {
    .rpc_call_prepare = calc_prepare,
    .rpc_call_done    = calc_done,
    .rpc_call_release = calc_release,
};

int calc_add_async(struct rpc_clnt *clnt, int a, int b, int *result)
{
    struct calc_data *cd;
    struct rpc_task *task;
    struct rpc_task_setup setup = { 0 };

    cd = kzalloc(sizeof(*cd), GFP_KERNEL);
    cd->args.a = a;
    cd->args.b = b;
    init_completion(&cd->done);

    setup.rpc_client   = clnt;
    setup.callback_ops = &calc_ops;
    setup.flags        = RPC_TASK_ASYNC;
    setup.callback_data = cd;

    task = rpc_run_task(&setup);
    if (IS_ERR(task)) {
        kfree(cd);
        return PTR_ERR(task);
    }

    // Wait for completion
    wait_for_completion(&cd->done);
    *result = cd->result.result;
    kfree(cd);
    return 0;
}
```

This does the same thing as `rpc_call_sync` but gives you more control — you can see the encode/decode steps and add custom logic at each stage.

## The rpc_message Shortcut

For simple cases (which is most cases), use `rpc_call_sync` with `struct rpc_message`:

```c
struct rpc_message msg = {
    .rpc_proc = &calc_procedures[ADD],
    .rpc_argp = &(struct calc_args){ .a = 3, .b = 4 },
    .rpc_resp = &result,
};

int ret = rpc_call_sync(clnt, &msg, 0);
if (ret == 0)
    pr_info("3 + 4 = %d\n", result.result);
else
    pr_err("RPC failed: %d\n", ret);
```

This is the pattern you'll use most often. Three fields: which procedure, what arguments, where results go. The RPC layer handles everything else.

## The Complete Client Call

Here's the complete function for our calculator client:

```c
int calc_add(struct rpc_clnt *clnt, int a, int b)
{
    struct calc_result result;
    struct rpc_message msg = {
        .rpc_proc = &calc_procedures[ADD],
        .rpc_argp = &(struct calc_args){ .a = a, .b = b },
        .rpc_resp = &result,
    };
    int ret;

    ret = rpc_call_sync(clnt, &msg, 0);
    if (ret < 0)
        return ret;

    if (result.error)
        return -EREMOTEIO;  // Server reported an error

    return result.result;
}
```

Usage:

```c
struct rpc_clnt *clnt = calc_create_client(&server);
int sum = calc_add(clnt, 3, 4);
if (sum < 0)
    pr_err("Addition failed: %d\n", sum);
else
    pr_info("3 + 4 = %d\n", sum);
rpc_destroy(clnt);
```

## Error Handling Patterns

`rpc_call_sync` returns:

| Value | Meaning |
|-------|---------|
| `0` | RPC completed. Check `result.error` (procedure-level error) |
| `-ETIMEDOUT` | Server didn't respond within timeout (all retries exhausted) |
| `-EIO` | Transport error (connection lost, can't reconnect) |
| `-EINTR` | Call was interrupted by a signal |
| `-EPROTO` | Protocol error (malformed reply) |
| `-EACCES` | Authentication failure |

Your code should handle at least these cases:

```c
int ret = rpc_call_sync(clnt, &msg, 0);
switch (ret) {
case 0:
    // Success — check procedure-level errors
    break;
case -ETIMEDOUT:
    pr_warn("Server unreachable\n");
    // Maybe try a different server
    break;
case -EACCES:
    pr_err("Authentication failure\n");
    // Maybe refresh credentials
    break;
default:
    pr_err("RPC error: %d\n", ret);
    break;
}
```

## Timeouts

Every RPC has a timeout. The default is typically 60 seconds. You can customize it:

```c
// Per-call timeout
int ret = rpc_call_sync(clnt, &msg, RPC_TASK_SOFT);
// With RPC_TASK_SOFT, the call returns -ETIMEDOUT instead of retrying forever
```

```c
// Custom timeout via rpc_clnt's timeout parameters
clnt->cl_timeout = &(struct rpc_timeout){
    .to_initval = 5 * HZ,      // 5 seconds initial timeout
    .to_retries = 3,            // Retry 3 times
    .to_maxval  = 20 * HZ,     // Max 20 seconds per retry
};
```

For our calculator, the defaults are fine. But knowing where to set them is useful when you need faster failover.

## The Full Client Lifecycle

```c
// 1. Create client
struct rpc_clnt *clnt = calc_create_client(&server);
if (IS_ERR(clnt))
    return PTR_ERR(clnt);

// 2. Make calls
int sum = calc_add(clnt, 3, 4);
int diff = calc_sub(clnt, 10, 4);
int product = calc_mul(clnt, 6, 7);
int quotient = calc_div(clnt, 10, 3);

// 3. Destroy client
rpc_destroy(clnt);
```

That's it. Three steps. The SunRPC layer handles connections, retries, encoding, decoding, and cleanup.
