import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import helpers
import main


class CrawlerResultTests(unittest.IsolatedAsyncioTestCase):
    async def crawl(self, advertised, heading, installer):
        browser = MagicMock()
        browser.new_context = AsyncMock()
        browser.new_context.return_value.new_page = AsyncMock()
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=playwright)
        manager.__aexit__ = AsyncMock(return_value=False)
        published_url = "https://portal.example.test/qualquer/endereco"
        with (
            patch.object(helpers, "async_playwright", return_value=manager),
            patch.object(helpers, "extract_latest_release_from_homepage", AsyncMock(
                return_value=(published_url, advertised)
            )),
            patch.object(helpers, "extract_release_page", AsyncMock(
                return_value=(published_url, heading, "notes")
            )) as release,
            patch.object(helpers, "extract_linux_link", AsyncMock(return_value=installer)),
        ):
            result = await helpers.run_pec_crawler()
        release.assert_awaited_once_with(
            browser.new_context.return_value.new_page.return_value, published_url
        )
        return result

    async def test_installer_version_takes_precedence_over_generic_heading(self):
        status, data = await self.crawl(
            "8.12", "8.12", "https://downloads.example.test/PEC-8.12.3-Linux64.jar"
        )
        self.assertEqual(status, "success")
        self.assertEqual(data["versao_label"], "8.12.3")

    async def test_rejects_installer_from_a_different_release_family(self):
        status, data = await self.crawl(
            "8.12", "8.12", "https://downloads.example.test/PEC-8.11.9-Linux64.jar"
        )
        self.assertEqual(status, "error")
        self.assertNotIn("versao_label", data)

    async def test_does_not_guess_another_page_when_published_page_has_no_linux(self):
        status, data = await self.crawl("8.12", "8.12", None)
        self.assertEqual(status, "error")
        self.assertIn("Linux", data["message"])

    async def test_full_version_can_come_from_heading_when_url_has_no_version(self):
        status, data = await self.crawl(
            None, "8.12.3", "https://downloads.example.test/get?platform=linux"
        )
        self.assertEqual(status, "success")
        self.assertEqual(data["versao_label"], "8.12.3")


class ScheduledJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_crawler_failure_marks_scheduled_job_as_failed_without_db(self):
        with patch.object(main, "run_pec_crawler", AsyncMock(return_value=(
            "error", {"message": "Não encontrei o link de download para Linux."}
        ))), patch.object(main, "get_session") as get_session:
            with self.assertRaisesRegex(RuntimeError, "link de download"):
                await main.daily_job()
            get_session.assert_not_called()
            self.assertEqual(main.LAST_RESULT["status"], "error")

    async def test_existing_version_finishes_successfully_without_saving(self):
        async def sessions():
            yield MagicMock()

        with (
            patch.object(main, "run_pec_crawler", AsyncMock(return_value=(
                "success", {"versao_label": "8.12.3", "release_page_html": "notes"}
            ))),
            patch.object(main, "get_session", sessions),
            patch.object(main, "get_version", AsyncMock(return_value=MagicMock())),
            patch.object(main, "save_version", AsyncMock()) as save,
            patch.object(main, "summarize_release_notes", AsyncMock()) as summarize,
        ):
            await main.daily_job()
            save.assert_not_awaited()
            summarize.assert_not_awaited()
            self.assertEqual(main.LAST_RESULT["status"], "success")
