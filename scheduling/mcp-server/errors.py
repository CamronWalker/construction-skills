"""Shared error types for the Westland Scheduler Local MCP server."""


class XerLockedError(Exception):
    """Raised when an XER file appears to be mid-write or otherwise unstable.

    The cache's partial-read guard reads the file's size twice with a short
    delay and raises this error when the two reads disagree, indicating that
    P6 (or another process) is still writing the file. Callers should retry
    after a short backoff rather than treat this as a permanent failure.
    """


class CachePinExhaustedError(Exception):
    """Raised when CpmCache.pin() is called but the pinned-entry count
    already equals max_entries. The cache cannot accept another pin without
    risking pin starvation. Callers should unpin something first.
    """


class XerValidationError(Exception):
    """Raised when an MCP tool wants to abort on validation failure rather
    than return the structured validation report. Carries the report in
    .report so the caller can still inspect it.
    """

    def __init__(self, message: str, report: dict | None = None) -> None:
        super().__init__(message)
        self.report = report or {}


class XerTemplateError(Exception):
    """Raised when create_xer_from_template can't load the named template
    (template file missing, malformed, or unknown template_name).
    """
