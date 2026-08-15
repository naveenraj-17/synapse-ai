"""
Blob storage: vaulted tool outputs, cached responses, run logs.

Everything here is content the engine writes that is too big, too transient, or
too file-shaped to be a database row. It used to live under ``DATA_DIR`` —
which meant it lived on one machine, and meant a shared process had every
tenant writing into one directory.

There are two implementations and one rule: **keys are prefixed by tenant**.
The prefix is applied here rather than by callers, so a caller that forgets is
not a cross-tenant leak — there is no way to ask for an unprefixed key.

    LocalBlobStore   a directory. The default; what a plain install uses.
    S3BlobStore      an S3 bucket, via the existing SynapseS3 client.

An embedder registers its own with ``set_blob_store()``.
"""
from core.storage.base import BlobStore, LocalBlobStore, get_blob_store, set_blob_store
from core.storage.s3 import S3BlobStore

__all__ = [
    "BlobStore",
    "LocalBlobStore",
    "S3BlobStore",
    "get_blob_store",
    "set_blob_store",
]
