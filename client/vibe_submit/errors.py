"""Client-side exceptions."""


class CollectError(Exception):
    """Raised when project collection violates size/count/traversal rules."""


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


class ServerChangeRequired(Exception):
    """Raised when a project-level server_url differs from the global config.

    The caller (CLI) must confirm the change interactively; library/MCP callers
    should surface this error and ask the user to confirm via CLI.
    """

    def __init__(self, url: str):
        self.url = url
        super().__init__(f"server URL change required: {url}")


class ApiError(Exception):
    """Raised for HTTP/network errors from the submission API."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        payload: dict | None,
    ):
        self.status = status
        self.code = code
        self.message = message
        self.payload = payload
        super().__init__(f"[{status}] {code}: {message}")


class OutboxError(Exception):
    """Raised when an outbox entry cannot be read or written."""

