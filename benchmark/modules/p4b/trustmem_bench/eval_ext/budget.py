"""Conservative, in-process reservation for a single model-evaluation worker."""

from threading import Lock


class BudgetCapReached(RuntimeError):
    pass


def require_positive_integer(value: int, field: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field} must be a positive integer")


class AttemptBudget:
    """Reserve a frozen charge bound before every transmitted attempt, including retries.

    Values are integer billionths of a US dollar. Reservations remain charged against
    the run cap even if usage is missing or the request fails. Pricing and the token
    bound must be established by an online transport before it can use this contract.
    """

    def __init__(self, cap_nano_usd: int, cap_attempts: int):
        require_positive_integer(cap_nano_usd, "cap_nano_usd")
        require_positive_integer(cap_attempts, "cap_attempts")
        self._cap_nano_usd = cap_nano_usd
        self._cap_attempts = cap_attempts
        self._reserved = 0
        self._attempts = 0
        self._lock = Lock()

    def reserve_attempt(self, bound_nano_usd: int) -> tuple[int, int]:
        require_positive_integer(bound_nano_usd, "bound_nano_usd")
        with self._lock:
            if self._attempts == self._cap_attempts or self._reserved + bound_nano_usd > self._cap_nano_usd:
                raise BudgetCapReached("Model attempt would exceed its frozen reservation cap")
            self._attempts += 1
            self._reserved += bound_nano_usd
            return self._attempts, self._reserved
