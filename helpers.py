import re
from playwright.async_api import (
    Error as PlaywrightError,
    Locator,
    Page,
    async_playwright,
)
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any
from urllib.parse import urljoin, urlsplit
import asyncio
import logging
from openai import AzureOpenAI

from env import settings
from parsing import (
    extract_homepage_version,
    extract_installer_version,
    extract_version,
    is_full_version,
)

logger = logging.getLogger(__name__)

LINUX_DOWNLOAD_BUTTON = re.compile(
    r"(?:download|vers[aã]o).*linux|linux", flags=re.IGNORECASE
)


def now_iso() -> str:
    ts = datetime.now(timezone.utc).isoformat()
    logger.debug("Generated timestamp %s", ts)
    return ts


async def extract_latest_post_from_blog(
    page: Page, base_url: str
) -> Tuple[str, Optional[str]]:
    logger.debug("Extracting latest post from blog")
    await page.goto(base_url)

    locator = page.locator("a[href*='/blog/versao-']").first
    if await locator.count() > 0:
        href = await locator.get_attribute("href") or ""
        text = await locator.text_content() or ""
        release_url = urljoin(base_url, href)
        versao = extract_version(text) or extract_version(href)
        return release_url, versao

    locator = page.locator("a", has_text="Leia Mais").first
    if await locator.count() > 0:
        href = await locator.get_attribute("href") or ""
        text = await locator.text_content() or ""
        release_url = urljoin(base_url, href)
        versao = extract_version(text) or extract_version(href)
        return release_url, versao

    raise ValueError("Não encontrei a URL do post da versão no Blog.")


async def resolve_control_url(page: Page, control: Locator) -> str:
    """Read a link or observe a click, without fetching its destination.

    The same operation resolves release pages and installers. Context routing
    includes the first navigation of a new tab; frame events cover SPA links.
    No URL templates or framework-specific handler inspection are needed.
    """
    href = await control.evaluate(
        "element => element.closest('a[href]')?.getAttribute('href') || null"
    )
    if href and not href.startswith("#"):
        target = urljoin(page.url, href)
        if urlsplit(target).scheme in ("http", "https") and target != page.url:
            return target

    destination = asyncio.get_running_loop().create_future()
    context = page.context
    original_pages = set(context.pages)
    original_url = page.url

    def record(url):
        if urlsplit(url).scheme in ("http", "https") and not destination.done():
            destination.set_result(url)

    async def intercept(route):
        request = route.request
        is_main_navigation = False
        if request.is_navigation_request():
            try:
                is_main_navigation = request.frame.parent_frame is None
            except PlaywrightError:
                # The first request of a popup precedes creation of its frame.
                is_main_navigation = True
        if is_main_navigation:
            # 204 prevents navigation and sends no request to the remote server.
            await route.fulfill(status=204)
            record(request.url)
        else:
            await route.fallback()

    def navigated(frame):
        if frame == page.main_frame and frame.url != original_url:
            record(frame.url)

    await context.route("**/*", intercept)
    page.on("framenavigated", navigated)
    try:
        await page.wait_for_load_state("load")
        await control.click(no_wait_after=True)
        try:
            return await asyncio.wait_for(destination, timeout=30)
        except asyncio.TimeoutError as exc:
            raise ValueError("O controle de download não informou um endereço HTTP(S).") from exc
    finally:
        page.remove_listener("framenavigated", navigated)
        await context.unroute("**/*", intercept)
        for popup in set(context.pages) - original_pages:
            await popup.close()


async def extract_linux_link(page: Page) -> Optional[str]:
    logger.debug("Searching for Linux download control")
    control = page.locator("a, button", has_text=LINUX_DOWNLOAD_BUTTON).first
    if await control.count() == 0:
        return None
    return await resolve_control_url(page, control)


async def extract_from_homepage(html: str) -> Optional[str]:
    logger.debug("Extracting version from homepage")
    return extract_homepage_version(html)


async def extract_latest_release_from_homepage(
    page: Page, base_url: str
) -> Tuple[str, Optional[str]]:
    """Follow the published download control, regardless of URL layout."""
    logger.debug("Discovering latest release from homepage %s", base_url)
    await page.goto(base_url, wait_until="load")

    control = page.locator(
        "a, button", has_text=re.compile(r"\bDownload\b", flags=re.IGNORECASE)
    ).first
    if await control.count() == 0:
        raise ValueError("Não encontrei o controle de download na página inicial.")

    text = await control.text_content() or ""
    advertised_version = extract_homepage_version(text)
    return await resolve_control_url(page, control), advertised_version


async def extract_release_page(
    page: Page, release_url: str
) -> Tuple[str, Optional[str], str]:
    """Extract the canonical URL, full version and release article HTML."""
    logger.debug("Extracting Docusaurus release page %s", release_url)
    response = await page.goto(release_url, wait_until="domcontentloaded")
    if response and not response.ok:
        raise ValueError(
            f"Página de release retornou HTTP {response.status}: {release_url}"
        )

    article = page.locator("article").first
    await article.wait_for(state="visible")

    heading = article.locator("h1").first
    heading_text = await heading.text_content() if await heading.count() else ""
    version = extract_version(heading_text or "")
    release_html = await article.inner_html()
    return page.url, version, release_html


async def summarize_release_notes(html: str) -> Optional[str]:
    logger.debug("Summarizing release notes")
    if (
        not html
        or not settings.AZURE_OPENAI_ENDPOINT
        or not settings.AZURE_OPENAI_API_KEY
    ):
        logger.debug("Skipping summarization due to missing HTML or Azure settings")
        return None

    client = AzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_version=settings.AZURE_OPENAI_API_VERSION,
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
            model=settings.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Conteúdo a ser resumido:{html}"},
            ],
            temperature=0.3,
            max_tokens=800,
        )

    response = await asyncio.to_thread(_call)
    message = response.choices[0].message
    summary = (getattr(message, "content", "") or "").strip()
    logger.debug("Generated summary with %d chars", len(summary))
    return summary


async def run_pec_crawler() -> Tuple[str, Dict[str, Any]]:
    try:
        logger.debug("Starting PEC crawler")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()

            (
                release_url,
                advertised_version,
            ) = await extract_latest_release_from_homepage(
                page, settings.BASE_URL
            )
            resolved_release_url, release_version, release_html = (
                await extract_release_page(page, release_url)
            )
            link_linux = await extract_linux_link(page)
            if not link_linux:
                raise ValueError("Não encontrei o link de download para Linux.")
            # Prefer the version in the actual installer to a generic heading.
            version_candidates = (
                extract_installer_version(link_linux),
                release_version,
                advertised_version,
            )
            versao_label = next(
                (version for version in version_candidates if is_full_version(version)),
                None,
            )
            if not versao_label:
                raise ValueError(
                    "Não encontrei uma versão completa (major.minor.patch) para persistir."
                )

            if advertised_version and versao_label.split(".")[:2] != advertised_version.split(".")[:2]:
                raise ValueError("A versão do instalador não pertence à família anunciada.")

            await browser.close()

        result = {
            "versao_label": versao_label,
            "url_release_page": resolved_release_url,
            "release_page_html": release_html,
            "link_linux": link_linux,
            "source": "sisaps docs",
            "timestamp": now_iso(),
            "crawler_version": "2.0.0",
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
