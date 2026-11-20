import os

import httpx


def validate_target(value: str) -> str:
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError("Enter an absolute HTTP or HTTPS URL without whitespace.")
    try:
        target = httpx.URL(value)
    except (httpx.InvalidURL, ValueError) as exc:
        raise ValueError("Enter a valid HTTP or HTTPS URL.") from exc
    if target.scheme not in ("http", "https") or not target.host:
        raise ValueError("Enter an absolute HTTP or HTTPS URL.")
    if "@" in value.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0] or "#" in value:
        raise ValueError("Remove credentials and fragments from the URL.")
    if target.port is not None and not 1 <= target.port <= 65535:
        raise ValueError("Enter a port between 1 and 65535.")
    allowed_hosts = {
        host.strip().lower()
        for host in os.getenv("ALLOWED_MONITOR_HOSTS", "demo").split(",") if host.strip()
    }
    if target.raw_host.decode() not in allowed_hosts:
        raise ValueError("This host is outside the configured allowlist.")
    return str(target)
