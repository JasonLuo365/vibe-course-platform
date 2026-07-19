from fastapi import Request


class PageAuthRequired(Exception):
    """Raised by page dependencies when teacher is not logged in."""

    def __init__(self, next_url: str = "/"):
        self.next_url = next_url
