import re
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any
from urllib.parse import urljoin

from env import settings

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def fetch_text(url: str) -> Tuple[str, str]:
    headers = {"User-Agent": "Mozilla/5.0 (+pec-crawler)"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, headers=headers) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text, str(r.url)

def extract_latest_post_from_blog(html: str, base_url: str) -> Tuple[str, Optional[str]]:
    soup = BeautifulSoup(html, "lxml")

    # Preferência: links do tipo /blog/versao-...
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = (a.get_text() or "").strip()
        if "/blog/versao-" in href:
            release_url = urljoin(base_url, href)
            m = re.search(r"(\d+\.\d+\.\d+)", text) or re.search(r"(\d+\.\d+\.\d+)", href)
            versao = m.group(1) if m else None
            return release_url, versao

    # Fallback: primeiro "Leia Mais"
    a = soup.find("a", string=lambda s: s and "Leia Mais" in s)
    if a and a.has_attr("href"):
        release_url = urljoin(base_url, a["href"])
        m = re.search(r"(\d+\.\d+\.\d+)", a.get_text(strip=True)) or re.search(r"(\d+\.\d+\.\d+)", release_url)
        versao = m.group(1) if m else None
        return release_url, versao

    raise ValueError("Não encontrei a URL do post da versão no Blog.")

def extract_linux_link(html: str, base_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")

    for a in soup.find_all("a", href=True):
        txt = (a.get_text() or "")
        if "Linux" in txt or "Versão para Linux" in txt or "Download para Linux" in txt:
            return urljoin(base_url, a["href"])

    # Fallback heurístico
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(k in href for k in ["linux", ".deb", ".rpm", ".zip"]):
            return urljoin(base_url, a["href"])

    return None

async def extract_from_homepage(html: str) -> Optional[str]:
    m = re.search(r"Download\s+Vers[aã]o\s+(\d+\.\d+\.\d+)", html, flags=re.IGNORECASE)
    return m.group(1) if m else None

async def run_pec_crawler() -> Tuple[str, Dict[str, Any]]:
    try:
        blog_html, blog_url = await fetch_text(settings.BLOG_URL)
        release_url, versao_label = extract_latest_post_from_blog(blog_html, blog_url)

        release_html, resolved_release_url = await fetch_text(release_url)
        link_linux = extract_linux_link(release_html, resolved_release_url)

        if not versao_label:
            home_html, _ = await fetch_text(settings.BASE_URL)
            versao_label = await extract_from_homepage(home_html)

        result = {
            "versao_label": versao_label,
            "url_release_page": resolved_release_url,
            "link_linux": link_linux,
            "source": "sisaps blog",
            "timestamp": now_iso(),
            "crawler_version": "1.0.0",
        }
        return "success", result
    except Exception as e:
        return "error", {
            "error": "crawler failed",
            "message": str(e),
            "timestamp": now_iso(),
        }

def parse_time_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)