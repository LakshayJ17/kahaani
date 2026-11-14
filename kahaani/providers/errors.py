class ProviderError(Exception):
    """A provider call failed. The fallback chain moves on to the next provider."""


class TransientError(ProviderError):
    """Worth retrying the same provider after a pause (HTTP 429, 5xx, timeouts).

    retry_after: seconds the provider asked us to wait, if it said.
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class QuotaExhausted(ProviderError):
    """Rate limited for longer than is worth waiting (e.g. a daily quota)."""
