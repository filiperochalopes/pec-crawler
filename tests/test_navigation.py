"""Browser-level contracts: URLs come from controls, never version templates."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from threading import Thread
import unittest
from unittest.mock import patch

from playwright.async_api import BrowserType, async_playwright

from helpers import (
    extract_latest_release_from_homepage,
    extract_linux_link,
    run_pec_crawler,
    settings,
)


class NavigationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright = await async_playwright().start()
        channel = os.environ.get("PEC_TEST_BROWSER_CHANNEL")
        self.browser = await self.playwright.chromium.launch(
            **({"channel": channel} if channel else {})
        )
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        self.requests = []
        self.html = ""

        async def fixture(route):
            self.requests.append(route.request.url)
            await route.fulfill(content_type="text/html; charset=utf-8", body=self.html)

        await self.context.route("**/*", fixture)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def test_follows_homepage_controls_to_arbitrary_addresses(self):
        destinations = [
            ("<a href='/publicacoes/atual?canal=estavel'>Download - Versão 8.12</a>",
             "https://portal.example.test/publicacoes/atual?canal=estavel"),
            ("<button onclick=\"location.href='/manual/instalacao'\">Download - Versão 8.12</button>",
             "https://portal.example.test/manual/instalacao"),
            ("<button onclick=\"window.open('https://releases.example.test/current')\">Download - Versão 8.12</button>",
             "https://releases.example.test/current"),
            ("<button onclick=\"history.pushState({}, '', '/app/release')\">Download - Versão 8.12</button>",
             "https://portal.example.test/app/release"),
            ("<a href='#' onclick=\"location.href='/outro/endereco'; return false\">Download - Versão 8.12</a>",
             "https://portal.example.test/outro/endereco"),
        ]
        for html, expected in destinations:
            with self.subTest(html=html):
                self.html = html
                url, version = await extract_latest_release_from_homepage(
                    self.page, "https://portal.example.test/"
                )
                self.assertEqual(url, expected)
                self.assertEqual(version, "8.12")

    async def test_resolves_linux_controls_without_fetching_installer(self):
        installer = "https://downloads.example.test/random/8.12.3/package-8.12.3-Linux64.jar"
        controls = [
            f"<a href='{installer}'>Linux</a>",
            f"<button onclick=\"location.href='{installer}'\">Download para Linux</button>",
            f"<button onclick=\"window.open('{installer}')\">Download para Linux</button>",
            f"<a href='{installer}'><button>Download para Linux</button></a>",
        ]
        for html in controls:
            with self.subTest(html=html):
                self.html = html
                await self.page.goto("https://portal.example.test/any-release")
                self.requests.clear()
                self.assertEqual(await extract_linux_link(self.page), installer)
                self.assertNotIn(installer, self.requests)

    async def test_homepage_does_not_need_a_version_in_the_control_label(self):
        self.html = "<a href='/releases/stable'>Download</a>"
        url, version = await extract_latest_release_from_homepage(
            self.page, "https://portal.example.test/"
        )
        self.assertEqual(url, "https://portal.example.test/releases/stable")
        self.assertIsNone(version)

    async def test_full_crawler_follows_published_destinations_and_redirects(self):
        """Runs the unmodified crawler over a real local HTTP server."""
        served = []

        class Portal(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                served.append(self.path)
                if self.path == "/":
                    body = ("<button onclick=\"location.href='/documentos/download-atual'\">"
                            "Download</button>")
                elif self.path == "/documentos/download-atual":
                    self.send_response(302)
                    self.send_header("Location", "/novidades/estavel")
                    self.end_headers()
                    return
                elif self.path == "/novidades/estavel":
                    body = ("<article><h1>Versão 8.12.3</h1>Notas da versão"
                            "<button onclick=\"window.open('/arquivos/get?platform=linux')\">"
                            "Linux</button></article>")
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Portal)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        home = f"http://127.0.0.1:{server.server_port}/"

        original_launch = BrowserType.launch

        async def launch(browser_type, *args, **kwargs):
            channel = os.environ.get("PEC_TEST_BROWSER_CHANNEL")
            if channel:
                kwargs["channel"] = channel
            return await original_launch(browser_type, *args, **kwargs)

        with (
            patch.object(settings, "BASE_URL", home),
            patch.object(BrowserType, "launch", launch),
        ):
            status, data = await run_pec_crawler()
        self.assertEqual(status, "success", data)
        self.assertEqual(data["versao_label"], "8.12.3")
        self.assertEqual(data["url_release_page"], home + "novidades/estavel")
        self.assertEqual(data["link_linux"], home + "arquivos/get?platform=linux")
        self.assertIn("Notas da versão", data["release_page_html"])
        # The installer address is resolved but never downloaded.
        self.assertNotIn("/arquivos/get?platform=linux", served)
        self.assertEqual(
            [p for p in served if p != "/favicon.ico"],
            ["/", "/documentos/download-atual", "/novidades/estavel"],
        )

    async def test_missing_linux_control_returns_none(self):
        self.html = "<article><a href='/windows.exe'>Windows</a></article>"
        await self.page.goto("https://portal.example.test/release")
        self.assertIsNone(await extract_linux_link(self.page))
