"""Small, dependency-free readiness probe for the local tunnel runtime."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HealthResult:
    ready: bool
    status_code: int | None
    detail: str


def check_ready(url: str, timeout: float = 3.0) -> HealthResult:
    request = Request(url, method="GET", headers={"User-Agent": "ARPHE-Windows-Bridge-Runtime/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            body = response.read(256).decode("utf-8", errors="replace").strip().lower()
            ready = status == 200 and body == "ready"
            return HealthResult(ready, status, "ready" if ready else "unexpected response")
    except HTTPError as exc:
        return HealthResult(False, int(exc.code), "HTTP error")
    except (URLError, TimeoutError, OSError):
        return HealthResult(False, None, "unreachable")
