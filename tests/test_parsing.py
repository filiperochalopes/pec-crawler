import unittest

from parsing import (
    build_release_url,
    extract_homepage_version,
    extract_linux_download_url,
    extract_version,
)


class VersionParsingTests(unittest.TestCase):
    def test_extracts_version_family_from_new_homepage_button(self):
        self.assertEqual(
            extract_homepage_version("Download para Linux - versão 5.5"), "5.5"
        )

    def test_keeps_legacy_three_part_homepage_version_compatible(self):
        self.assertEqual(extract_homepage_version("Download Versão 5.4.18"), "5.4.18")

    def test_extracts_full_version_from_release_heading(self):
        self.assertEqual(extract_version("Versão 5.5.22 - 10/07/2026"), "5.5.22")

    def test_extracts_linux_url_from_react_handler(self):
        handler = (
            '()=>{window.location.href="https://arquivos.esusaps.ufsc.br/PEC/'
            'hash/5.5.22/eSUS-AB-PEC-5.5.22-Linux64.jar"}'
        )
        self.assertEqual(
            extract_linux_download_url(handler),
            "https://arquivos.esusaps.ufsc.br/PEC/hash/5.5.22/"
            "eSUS-AB-PEC-5.5.22-Linux64.jar",
        )

    def test_builds_docusaurus_release_url_from_version_family(self):
        self.assertEqual(
            build_release_url(
                "https://sisaps.saude.gov.br/sistemas/esusaps/docs/Versoes/", "5.5"
            ),
            "https://sisaps.saude.gov.br/sistemas/esusaps/docs/Versoes/versao_5_5",
        )

    def test_uses_major_minor_when_full_version_is_provided(self):
        self.assertEqual(
            build_release_url("https://example.test/docs/Versoes/", "5.5.22"),
            "https://example.test/docs/Versoes/versao_5_5",
        )


if __name__ == "__main__":
    unittest.main()
