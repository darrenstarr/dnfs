# Chapter 0: Preface — What You're About to Read

## The Shape of This Book

Most books about NFS fall into one of two camps. There are the RFC commentaries — line-by-line dissections of the protocol specifications that tell you *what* the bytes on the wire mean but never *why* they are what they are. Then there are the "admin guides" that show you which flags to pass to `mount` without ever explaining what the flag does inside the kernel.

This book is neither of those things.

This is a book about **architectural reasoning**. Every feature in the NFS protocol exists because someone encountered a real, painful problem — a locked file that couldn't be recovered, a server reboot that took down an entire datacenter, a 10-gigabit link running at 500 megabits because the protocol couldn't keep the pipe full. I want you to understand the problem first, then watch the protocol evolve to solve it, and finally see how that solution is realized in the Linux kernel source code.

You will come away from this book understanding not just how NFS works, but **why it works the way it does**.

## Who This Book Is For

I'm writing for two kinds of readers.

The first is a kernel developer or systems programmer who needs to modify the NFS client. You need to understand the `rpc_xprt_switch` and the `xps_iter_ops` dispatch path because you're about to implement a custom multipath policy. You need to know why the session slot table exists before you can understand why your new feature must participate in slot-based ordering. This book gives you the architectural grounding to make correct design decisions.

The second reader is a storage architect or senior operations engineer who's trying to understand why their NFS deployment behaves the way it does. Why does a server reboot cause a 90-second I/O stall? Why doesn't adding a second NIC double your throughput? Why does NFSv4.1 session trunking exist but not work with your storage array? These questions don't have answers in the RFCs. They have answers in the engineering tradeoffs that the protocol designers made — tradeoffs this book will explain.

## A Note on NFSv3

I treat NFSv3 as **legacy architecture**. I don't mean "old and useless" — NFSv3 is still widely deployed and will remain so for years. I mean that its architectural approach (stateless server, separate lock manager, no delegation, no session) is a dead end for the features we care about: multipath, parallel access, and transparent failover.

Where NFSv3's design illuminates *why* NFSv4 made a particular choice, I discuss it. But the book's focus is on NFSv4 and NFSv4.1 — the stateful, session-oriented protocol that forms the foundation for distributed NFS access.

## Sun RPC Is Prerequisite

I assume you know what Remote Procedure Calls are at a high level. You understand that an RPC layer serializes function arguments, sends them over a network, and deserializes the response. You know what a portmapper does.

If you've never heard of XDR or don't know the difference between AUTH_SYS and RPCSEC_GSS, Chapter 2 will give you enough context. But it's a recap, not a tutorial — I cover just enough to make the NFS chapters self-contained.

## The Kernel Version

All code references and implementation descriptions target **Linux 7.0.0** kernel source, specifically the `linux-source-7.0.0` package from **Ubuntu 26.04 LTS** (codenamed Resolute). The running kernel version on our test systems is `7.0.0-14-generic`.

If you're reading this on a later kernel, the broad architecture will be the same. The NFS client code evolves slowly — the fundamental structures (`rpc_clnt`, `xprt_switch`, `nfs_client`, `nfs4_session`) have been stable for years.

## Diagrams

Every architectural concept in this book is accompanied by a diagram. I use Mermaid syntax, which renders natively in GitHub's Markdown viewer. If you're reading this in a different format and the diagrams don't render, the surrounding text should be sufficient — the diagrams illustrate, they don't define.

## How to Read This Book

You can read it sequentially, but I expect most readers will jump around. If you're here for the multipath design, start with Chapter 5 and refer back to earlier chapters when you encounter a concept you don't recognize. If you're debugging an NFSv4.1 session issue, start with Chapter 4.

The one thing I ask is this: don't skip the "why" sections. The NFS protocol has accumulated forty years of engineering wisdom. Every design choice — the COMPOUND RPC model, the session slot table, the separation of layout and data in pNFS — exists because someone learned a hard lesson. Those lessons are worth understanding, even if your immediate concern is just getting a mount option to parse correctly.

---

**Chapter 1** begins at the beginning: why NFSv2 looked the way it did, what v3 fixed, and why none of it was enough.
