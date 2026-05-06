# Appendix A: On-Wire Protocol Reference

## NFSv4 Operations

| Operation | Number | RFC Section | Idempotent |
|-----------|--------|-------------|------------|
| ACCESS | 3 | 18.1 | Y |
| CLOSE | 4 | 18.2 | N |
| COMMIT | 5 | 18.3 | Y |
| CREATE | 6 | 18.4 | N |
| DELEGPURGE | 7 | 18.5 | N |
| DELEGRETURN | 8 | 18.6 | N |
| GETATTR | 9 | 18.7 | Y |
| GETFH | 10 | 18.8 | Y |
| LINK | 11 | 18.9 | N |
| LOCK | 12 | 18.10 | N |
| LOCKT | 13 | 18.11 | Y |
| LOCKU | 14 | 18.12 | N |
| LOOKUP | 15 | 18.13 | Y |
| LOOKUPP | 16 | 18.14 | Y |
| NVERIFY | 17 | 18.15 | Y |
| OPEN | 18 | 18.16 | N |
| OPEN_CONFIRM | 19 | 18.17 | N |
| OPEN_DOWNGRADE | 20 | 18.18 | N |
| PUTFH | 21 | 18.19 | Y |
| PUTPUBFH | 22 | 18.20 | Y |
| PUTROOTFH | 23 | 18.21 | Y |
| READ | 24 | 18.22 | Y |
| READDIR | 25 | 18.23 | Y |
| READLINK | 26 | 18.24 | Y |
| REMOVE | 27 | 18.25 | N |
| RENAME | 28 | 18.26 | N |
| RENEW | 29 | 18.27 | N |
| RESTOREFH | 30 | 18.28 | Y |
| SAVEFH | 31 | 18.29 | Y |
| SECINFO | 32 | 18.30 | Y |
| SETATTR | 33 | 18.31 | N |
| SETCLIENTID | 34 | 18.32 | N |
| SETCLIENTID_CONFIRM | 35 | 18.33 | N |
| VERIFY | 36 | 18.34 | Y |
| WRITE | 38 | 18.36 | N |
| RELEASE_LOCKOWNER | 39 | 18.37 | N |
| BACKCHANNEL_CTL | 40 | 18.38 | N |
| BIND_CONN_TO_SESSION | 41 | 18.39 | N |
| EXCHANGE_ID | 42 | 18.40 | N |
| CREATE_SESSION | 43 | 18.41 | N |
| DESTROY_SESSION | 44 | 18.42 | N |
| FREE_STATEID | 45 | 18.43 | N |
| GET_DIR_DELEGATION | 46 | 18.44 | N |
| GETDEVICEINFO | 47 | 18.45 | Y |
| GETDEVICELIST | 48 | 18.46 | Y |
| LAYOUTCOMMIT | 49 | 18.47 | N |
| LAYOUTGET | 50 | 18.48 | Y |
| LAYOUTRETURN | 51 | 18.49 | N |
| RECLAIM_COMPLETE | 52 | 18.50 | N |
| SECINFO_NO_NAME | 53 | 18.51 | Y |
| SEQUENCE | 54 | 18.52 | N |
| SET_SSV | 55 | 18.53 | N |
| TEST_STATEID | 56 | 18.54 | Y |
| WANT_DELEGATION | 57 | 18.55 | N |
| DESTROY_CLIENTID | 58 | 18.56 | N |
| RECLAIM_OPEN | 59 | 18.57 | N |

## NFSv4 Error Codes

| Code | Name | Meaning |
|------|------|---------|
| 0 | NFS4_OK | Success |
| 1 | NFS4ERR_PERM | Permission denied |
| 2 | NFS4ERR_NOENT | No such file/directory |
| 3 | NFS4ERR_IO | I/O error |
| 4 | NFS4ERR_NXIO | No such device |
| 6 | NFS4ERR_ACCES | Permission denied |
| 13 | NFS4ERR_EXIST | File exists |
| 17 | NFS4ERR_XDEV | Cross-device link |
| 18 | NFS4ERR_NOTDIR | Not a directory |
| 19 | NFS4ERR_ISDIR | Is a directory |
| 20 | NFS4ERR_INVAL | Invalid argument |
| 22 | NFS4ERR_FBIG | File too large |
| 27 | NFS4ERR_NOSPC | No space left |
| 28 | NFS4ERR_ROFS | Read-only filesystem |
| 30 | NFS4ERR_MLINK | Too many links |
| 31 | NFS4ERR_NAMETOOLONG | Name too long |
| 63 | NFS4ERR_NOTEMPTY | Directory not empty |
| 66 | NFS4ERR_DQUOT | Disk quota exceeded |
| 69 | NFS4ERR_STALE | Stale filehandle |
| 70 | NFS4ERR_BADHANDLE | Bad filehandle |
| 71 | NFS4ERR_BAD_COOKIE | READDIR cookie invalid |
| 72 | NFS4ERR_NOTSUPP | Operation not supported |
| 73 | NFS4ERR_TOOSMALL | Buffer too small |
| 74 | NFS4ERR_SERVERFAULT | Server fault |
| 75 | NFS4ERR_BADTYPE | Bad type |
| 76 | NFS4ERR_JUKED | Resource exhausted |
| 10001 | NFS4ERR_DELEG_ALREADY_WANTED | Delegation already wanted |
| 10002 | NFS4ERR_BACK_CHAN_BUSY | Backchannel busy |
| 10003 | NFS4ERR_BADCHAR | Bad character in UTF-8 |
| 10004 | NFS4ERR_BADNAME | Bad name |
| 10005 | NFS4ERR_BAD_RANGE | Bad lock range |
| 10006 | NFS4ERR_BAD_XDR | Bad XDR encoding |
| 10007 | NFS4ERR_BADHIGHSLOT | Bad highest slot |
| 10008 | NFS4ERR_BADSLOT | Bad slot |
| 10009 | NFS4ERR_BADSRVID | Bad server ID |
| 10010 | NFS4ERR_BADSTATEID | Bad stateid |
| 10011 | NFS4ERR_BAD_SEQID | Bad sequence ID |
| 10012 | NFS4ERR_BADSESSION | Bad session |
| 10013 | NFS4ERR_BAD_XATTR | Bad extended attribute |
| 10014 | NFS4ERR_CB_PATH_DOWN | Callback path down |
| 10015 | NFS4ERR_CLID_INUSE | Client ID in use |
| 10016 | NFS4ERR_CONN_NOT_BOUND_TO_SESSION | Connection not bound |
| 10017 | NFS4ERR_DEADSESSION | Session dead |
| 10018 | NFS4ERR_DELAY | Transient error (retry) |
| 10019 | NFS4ERR_EXPIRED | Lease expired |
| 10020 | NFS4ERR_FHEXPIRED | Filehandle expired |
| 10021 | NFS4ERR_GRACE | Server in grace period |
| 10022 | NFS4ERR_LEASE_MOVED | Lease moved |
| 10023 | NFS4ERR_LOCKS_HELD | Locks held |
| 10024 | NFS4ERR_LOCK_NOTSUPP | Lock type not supported |
| 10025 | NFS4ERR_LOCK_RANGE | Lock range conflict |
| 10026 | NFS4ERR_MINOR_VERS_MISMATCH | Minor version mismatch |
| 10027 | NFS4ERR_MLINK | Too many links |
| 10028 | NFS4ERR_MOVED | Filesystem migrated |
| 10029 | NFS4ERR_NO_GRACE | No grace period |
| 10030 | NFS4ERR_NOENT | No such entry |
| 10031 | NFS4ERR_NOFILEHANDLE | No filehandle |
| 10032 | NFS4ERR_NOT_ONLY_OP | Not only operation |
| 10033 | NFS4ERR_NOT_SAME | Not same |
| 10034 | NFS4ERR_NOXATTR | No extended attribute |
| 10035 | NFS4ERR_OLD_STATEID | Stateid expired |
| 10036 | NFS4ERR_OPENMODE | Open mode error |
| 10037 | NFS4ERR_OP_ILLEGAL | Illegal operation |
| 10038 | NFS4ERR_PNFS_IO_HOLE | pNFS I/O hole |
| 10039 | NFS4ERR_PNFS_NO_LAYOUT | No layout |
| 10040 | NFS4ERR_RECALLCONFLICT | Recall conflict |
| 10041 | NFS4ERR_REJECT_DELEG | Reject delegation |
| 10042 | NFS4ERR_REP_TOO_BIG | Reply too big |
| 10043 | NFS4ERR_REP_TOO_BIG_TO_CACHE | Reply too big to cache |
| 10044 | NFS4ERR_REQ_TOO_BIG | Request too big |
| 10045 | NFS4ERR_RESOURCE | Resource limit |
| 10046 | NFS4ERR_RETRY_UNCACHED_REP | Retry uncached reply |
| 10047 | NFS4ERR_RETRY_UNCACHED_REP | Retry uncached |
| 10048 | NFS4ERR_SAME | Same |
| 10049 | NFS4ERR_SHARE_DENIED | Share denied |
| 10050 | NFS4ERR_STALE_CLIENTID | Stale client ID |
| 10051 | NFS4ERR_STALE_STATEID | Stale stateid |
| 10052 | NFS4ERR_SYMLINK | Symlink encountered |
| 10053 | NFS4ERR_TOO_MANY_OPS | Too many operations |
| 10054 | NFS4ERR_UNKNOWN_LAYOUTTYPE | Unknown layout type |
| 10055 | NFS4ERR_UNKNOWN_SECINFO | Unknown security info |
| 10056 | NFS4ERR_UNSUPP_CHARSET | Unsupported charset |
| 10057 | NFS4ERR_WRONGSEC | Wrong security flavour |
| 10058 | NFS4ERR_WRONG_LFS | Wrong logical filesystem |
| 10059 | NFS4ERR_WRONG_TYPE | Wrong type |

## COMPOUND RPC Wire Format

```xdr
// NFSv4.1 COMPOUND request
struct COMPOUND4args {
    utf8str_cs    tag;            // debugging tag
    uint32_t      minorversion;   // 1 for v4.1
    nfs_opnum4    argarray<>;     // variable-length operation array
};

// Each operation in argarray:
struct nfs_argop4 {
    nfs_opnum4    op;
    union {
        // op-specific arguments...
        ACCESS4args       opaccess;
        CLOSE4args        opclose;
        COMMIT4args       opcommit;
        // ... one per operation number
    } op;
};
```

## XDR Primitive Types

| Type | Wire Size | Description |
|------|-----------|-------------|
| `int` / `unsigned int` | 4 bytes | Signed/unsigned 32-bit integer |
| `hyper` / `unsigned hyper` | 8 bytes | Signed/unsigned 64-bit integer |
| `string` | 4 + data + padding | Length-prefixed UTF-8 string |
| `opaque` | 4 + data + padding | Length-prefixed byte array |
| `stateid4` | 16 bytes | State identifier (see RFC 5661 §2.4) |
| `verifier4` | 8 bytes | Client or server verifier |
| `nfs_cookie4` | 8 bytes | READDIR cookie |
| `nfs_ftype4` | 4 bytes | File type enumeration |
| `bitmap4` | variable | Attribute bitmap mask |
