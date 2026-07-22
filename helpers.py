import re
from playwright.async_api import async_playwright, Page
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

async def extract_latest_post_from_blog(page: Page, base_url: str) -> Tuple[str, Optional[str]]:
    logger.debug("Extracting latest post from blog")
    await page.goto(base_url)

    locator = page.locator("a[href*='/blog/versao-']").first
    if await locator.count() > 0:
        href = await locator.get_attribute("href") or ""
        text = await locator.text_content() or ""
        release_url = urljoin(base_url, href)
        m = re.search(r"(\d+\.\d+\.\d+)", text) or re.search(r"(\d+\.\d+\.\d+)", href)
        versao = m.group(1) if m else None
        return release_url, versao

    locator = page.locator("a", has_text="Leia Mais").first
    if await locator.count() > 0:
        href = await locator.get_attribute("href") or ""
        text = await locator.text_content() or ""
        release_url = urljoin(base_url, href)
        m = re.search(r"(\d+\.\d+\.\d+)", text) or re.search(r"(\d+\.\d+\.\d+)", href)
        versao = m.group(1) if m else None
        return release_url, versao

    raise ValueError("Não encontrei a URL do post da versão no Blog.")

async def extract_linux_link(page: Page) -> Optional[str]:
    logger.debug("Searching for Linux download link")
    button = page.locator("button", has_text="Linux").first
    if await button.count() == 0:
        logger.debug("Linux link not found")
        return None

    async with page.expect_download() as download_info:
        await button.click()
    download = await download_info.value
    link = download.url
    return link

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
    message = response.choices[0].message
    summary = getattr(message, "content", "").strip()
    logger.debug("Generated summary with %d chars", len(summary))
    return summary

async def run_pec_crawler() -> Tuple[str, Dict[str, Any]]:
    try:
        logger.debug("Starting PEC crawler")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()

            release_url, versao_label = await extract_latest_post_from_blog(page, settings.BLOG_URL)

            await page.goto(release_url)
            resolved_release_url = page.url
            release_html = await page.content()
            link_linux = await extract_linux_link(page)

            if not link_linux:
                raise ValueError("Linux download link not found")

            if not versao_label:
                await page.goto(settings.BASE_URL)
                home_html = await page.content()
                versao_label = await extract_from_homepage(home_html)

            await browser.close()

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
