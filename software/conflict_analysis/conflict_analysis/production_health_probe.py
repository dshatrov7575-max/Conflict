"""HTTP readiness probe used by the production container healthcheck."""

from __future__ import annotations

import http.client
import os


def _host() -> str:
    for item in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(","):
        candidate = item.strip()
        if candidate:
            return candidate
    raise RuntimeError("DJANGO_ALLOWED_HOSTS has no readiness host")


def main() -> None:
    connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
    try:
        connection.request(
            "GET",
            "/health/ready/",
            headers={
                "Host": _host(),
                "X-Forwarded-Proto": "https",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        body = response.read()
    finally:
        connection.close()
    if response.status != 200 or body != b"READY\n":
        raise SystemExit(
            f"production readiness failed: status={response.status} body={body!r}"
        )


if __name__ == "__main__":
    main()
