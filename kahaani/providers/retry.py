import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

from kahaani.providers.errors import QuotaExhausted, TransientError

log = logging.getLogger(__name__)
T = TypeVar("T")

# If a provider asks us to wait longer than this, give up and let the
# fallback chain try the next provider instead.
MAX_WAIT = 65.0


def with_retries(
    fn: Callable[[], T],
    *,
    attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
    max_wait: float = MAX_WAIT,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call fn, retrying TransientError with exponential backoff and jitter.

    Honours the provider's retry_after when given.
    """
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except TransientError as e:
            if e.retry_after is not None and e.retry_after > max_wait:
                raise QuotaExhausted(f"{e} (asked to wait {e.retry_after:.0f}s)") from e
            if attempt == attempts:
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1)) * random.uniform(0.5, 1.0)
            if e.retry_after is not None:
                delay = max(delay, e.retry_after + 0.5)
            log.warning(
                "transient error (%s), retry %d/%d in %.1fs", e, attempt, attempts - 1, delay
            )
            sleep(delay)
    raise AssertionError("unreachable")
