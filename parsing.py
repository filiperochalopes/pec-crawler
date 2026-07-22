import re
from typing import Optional
from urllib.parse import urljoin


VERSION_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)")
LINUX_DOWNLOAD_PATTERN = re.compile(
    r"https?://[^\s\"'<>]*Linux[^\s\"'<>]*\.(?:jar|zip)(?:\?[^\s\"'<>]*)?",
    flags=re.IGNORECASE,
)


def extract_version(text: str) -> Optional[str]:
    """Return a major.minor or major.minor.patch version found in text."""
    match = VERSION_PATTERN.search(text or "")
    return match.group(1) if match else None


def extract_homepage_version(text: str) -> Optional[str]:
    """Extract the version advertised by a Windows/Linux download control."""
    match = re.search(
        r"Download(?:\s+para\s+(?:Windows|Linux))?\s*-?\s*"
        r"Vers[aã]o\s+(\d+\.\d+(?:\.\d+)?)",
        text or "",
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def extract_linux_download_url(text: str) -> Optional[str]:
    """Extract a Linux installer URL from an href or JavaScript handler."""
    match = LINUX_DOWNLOAD_PATTERN.search(text or "")
    return match.group(0) if match else None


def build_release_url(releases_url: str, version: str) -> str:
    """Build the Docusaurus release URL from the advertised version family."""
    parts = version.split(".")
    if len(parts) < 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Versão inválida para página de release: {version!r}")

    release_slug = "_".join(parts[:2])
    return urljoin(releases_url.rstrip("/") + "/", f"versao_{release_slug}")
