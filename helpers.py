import re
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any
from urllib.parse import urljoin
import asyncio
import logging
from openai import AzureOpenAI

from env import settings

logger = logging.getLogger(__name__)

def now_iso() -> str:
    ts = datetime.now(timezone.utc).isoformat()
    logger.debug("Generated timestamp %s", ts)
    return ts

async def fetch_text(url: str) -> Tuple[str, str]:
    logger.debug("Fetching URL: %s", url)
    headers = {"User-Agent": "Mozilla/5.0 (+pec-crawler)"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, headers=headers) as client:
        r = await client.get(url)
        r.raise_for_status()
        logger.debug("Fetched %s with status %s", r.url, r.status_code)
        return r.text, str(r.url)

def extract_latest_post_from_blog(html: str, base_url: str) -> Tuple[str, Optional[str]]:
    logger.debug("Extracting latest post from blog")
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
    logger.debug("Searching for Linux download link")
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

    logger.debug("Linux link not found")
    return None

async def extract_from_homepage(html: str) -> Optional[str]:
    logger.debug("Extracting version from homepage")
    m = re.search(r"Download\s+Vers[aã]o\s+(\d+\.\d+\.\d+)", html, flags=re.IGNORECASE)
    return m.group(1) if m else None


async def summarize_release_notes(html: str) -> Optional[str]:
    logger.debug("Summarizing release notes")
    if not html or not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_API_KEY:
        logger.debug("Skipping summarization due to missing HTML or Azure settings")
        return None

    client = AzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_version="2024-02-15-preview",
        api_key=settings.AZURE_OPENAI_API_KEY,
    )

    system_prompt = (
        "Você é um assistente que transforma conteúdos técnicos em comunicados claros e objetivos "
        "sobre atualizações de software. Utilize sempre o seguinte modelo de resumo:\n\n"
        "<p>🚀 A versão <strong>[versão]</strong> do Prontuário Eletrônico do Cidadão (e-SUS APS) foi "
        "lançada em [data] e já está disponível nos ambientes de produção e treinamento.</p>\n\n"
        "<p>Principais destaques da atualização:</p>\n• <ul><li>[<strong>item 1<strong/> resumido com clareza e sem termos técnicos excessivos]\n"
        "• [<strong>item 2</strong> descrição]\n• [...]\n\n"
        "Seu trabalho é aplicar esse modelo com base no conteúdo a seguir e retornar apenas o HTML dentro de uma tag <article>, sem <html>, <head> ou <body>."
    )

    def _call():
        return client.chat.completions.create(
            model="gpt-4o-2024-05-13",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Conteúdo a ser resumido:{html}"},
            ],
            temperature=0.3,
            max_tokens=800,
        )

    response = await asyncio.to_thread(_call)
    summary = response.choices[0].message["content"].strip()
    logger.debug("Generated summary with %d chars", len(summary))
    return summary

async def run_pec_crawler() -> Tuple[str, Dict[str, Any]]:
    try:
        logger.debug("Starting PEC crawler")
        blog_html, blog_url = await fetch_text(settings.BLOG_URL)
        release_url, versao_label = extract_latest_post_from_blog(blog_html, blog_url)

        release_html, resolved_release_url = await fetch_text(release_url)
        link_linux = extract_linux_link(release_html, resolved_release_url)

        if not link_linux:
            raise ValueError("Linux download link not found")

        if not versao_label:
            home_html, _ = await fetch_text(settings.BASE_URL)
            versao_label = await extract_from_homepage(home_html)

        result = {
            "versao_label": versao_label,
            "url_release_page": resolved_release_url,
            "release_page_html": release_html,
            "link_linux": link_linux,
            "source": "sisaps blog",
            "timestamp": now_iso(),
            "crawler_version": "1.0.0",
        }
        logger.debug("Crawler result: %s", result)
        return "success", result
    except Exception as e:
        logger.debug("Crawler failed: %s", e)
        return "error", {
            "error": "crawler failed",
            "message": str(e),
            "timestamp": now_iso(),
        }

def parse_time_hhmm(s: str) -> tuple[int, int]:
    logger.debug("Parsing time string: %s", s)
    h, m = s.split(":")
    return int(h), int(m)
