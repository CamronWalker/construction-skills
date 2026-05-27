"""Shared error types for the Westland Scheduler Local MCP server."""


class XerLockedError(Exception):
    """Raised when an XER file appears to be mid-write or otherwise unstable.

    The cache's partial-read guard reads the file's size twice with a short
    delay and raises this error when the two reads disagree, indicating that
    P6 (or another process) is still writing the file. Callers should retry
    after a short backoff rather than treat this as a permanent failure.
    """
