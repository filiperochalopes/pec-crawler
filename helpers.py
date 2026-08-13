import re
from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any
from urllib.parse import urljoin
import asyncio
import logging
from openai import AzureOpenAI

from env import settings
from parsing import (
    build_release_blog_url,
    build_release_url,
    extract_homepage_version,
    extract_linux_download_url,
    extract_version,
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


async def extract_linux_link(page: Page) -> Optional[str]:
    logger.debug("Searching for Linux download link")
    button = page.locator(
        "button", has_text=LINUX_DOWNLOAD_BUTTON
    ).first
    if await button.count() == 0:
        logger.debug("Linux link not found")
        return None

    # Prefer declarative markup if the portal adopts a normal link later.
    anchor_href = await button.evaluate(
        "element => element.closest('a') ? element.closest('a').href : null"
    )
    link = extract_linux_download_url(anchor_href or "")
    if link:
        return link

    # The current Docusaurus page attaches the URL in a React onClick prop,
    # rather than exposing it as an href. Wait for hydration, then read the
    # handler without executing it or starting the very large JAR download.
    button_handle = await button.element_handle()
    if button_handle:
        try:
            await page.wait_for_function(
                """element => Object.keys(element).some(
                    key => key.startsWith('__reactProps$')
                )""",
                arg=button_handle,
                timeout=10_000,
            )
        except PlaywrightTimeoutError:
            logger.debug("React props were not available on the Linux button")

        handler_source = await button.evaluate(
            """element => {
                const key = Object.keys(element).find(
                    key => key.startsWith('__reactProps$')
                );
                const handler = key && element[key] && element[key].onClick;
                return handler ? handler.toString() : '';
            }"""
        )
        link = extract_linux_download_url(handler_source or "")
        if link:
            return link

    # The homepage uses a React onClick handler instead of an anchor. Capture the
    # resulting installer request as a fallback, but abort it: the crawler only
    # needs its URL and downloading the full JAR wastes time, memory and disk.
    download_request = asyncio.get_running_loop().create_future()
    linux_installer_pattern = re.compile(
        r"Linux[^/?]*\.(?:jar|zip)(?:[?#]|$)", re.IGNORECASE
    )

    async def capture_download(route):
        if not download_request.done():
            download_request.set_result(route.request.url)
        await route.abort()

    await page.route(linux_installer_pattern, capture_download)
    click_error = None
    try:
        try:
            await button.click(no_wait_after=True)
        except Exception as exc:
            # An aborted navigation may surface on the click. Preserve it and
            # only re-raise when no matching installer request was captured.
            click_error = exc

        try:
            return await asyncio.wait_for(download_request, timeout=30)
        except asyncio.TimeoutError as exc:
            if click_error:
                raise click_error
            raise ValueError(
                "O botão Linux não iniciou uma requisição de download."
            ) from exc
    finally:
        await page.unroute(linux_installer_pattern, capture_download)


async def extract_from_homepage(html: str) -> Optional[str]:
    logger.debug("Extracting version from homepage")
    return extract_homepage_version(html)


async def extract_latest_release_from_homepage(
    page: Page, base_url: str, releases_url: str
) -> Tuple[str, str]:
    """Discover the current release post from the homepage.

    SISAPS used to expose platform-specific buttons on this page.  The current
    site has one generic button which points to a versioned blog post, where the
    Linux installer control lives.  Keep the version extraction independent of
    the button label so both layouts work.
    """
    logger.debug("Discovering latest release from homepage %s", base_url)
    await page.goto(base_url, wait_until="domcontentloaded")

    button = page.locator(
        "button", has_text=re.compile(r"Download.*Vers[aã]o", flags=re.IGNORECASE)
    ).first
    if await button.count() == 0:
        raise ValueError(
            "Não encontrei o botão de download na página inicial."
        )

    button_text = await button.text_content() or ""
    advertised_version = extract_homepage_version(button_text)
    if not advertised_version:
        advertised_version = extract_homepage_version(await page.content())
    if not advertised_version:
        raise ValueError("Não encontrei a versão atual na página inicial.")

    # Since 2026 the versioned blog post is the canonical release page.  The
    # old documentation URL is retained as a fallback for portals that still
    # publish only a major/minor version on the homepage.
    if advertised_version.count(".") >= 2:
        return build_release_blog_url(base_url, advertised_version), advertised_version
    return build_release_url(releases_url, advertised_version), advertised_version


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
                page, settings.BASE_URL, settings.RELEASES_URL
            )
            (
                resolved_release_url,
                release_version,
                release_html,
            ) = await extract_release_page(page, release_url)
            link_linux = await extract_linux_link(page)
            if not link_linux:
                raise ValueError("Não encontrei o link de download para Linux.")
            # The release article may identify only a major/minor family (for
            # example, 5.5). The installer URL contains the specific published
            # build, so it is the canonical value to persist.
            versao_label = (
                extract_version(link_linux)
                or release_version
                or advertised_version
            )

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
