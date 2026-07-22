import os
from dataclasses import dataclass
from urllib.parse import urljoin


@dataclass
class Settings:
    APP_NAME: str = "PEC Crawler API"
    TZ: str = os.getenv("TZ", "America/Bahia")
    RUN_AT: str = os.getenv("RUN_AT", "07:00")  # HH:MM
    BASE_URL: str = os.getenv(
        "BASE_URL", "https://sisaps.saude.gov.br/sistemas/esusaps/"
    )
    BLOG_PATH: str = os.getenv("BLOG_PATH", "blog/")
    RELEASES_PATH: str = os.getenv("RELEASES_PATH", "docs/Versoes/")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://pec:changeme@db:5432/pec"
    )
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_DEPLOYMENT: str = os.getenv(
        "AZURE_OPENAI_DEPLOYMENT", "gpt-4o-2024-05-13"
    )
    AZURE_OPENAI_API_VERSION: str = os.getenv(
        "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
    )

    @property
    def BLOG_URL(self) -> str:
        return urljoin(self.BASE_URL, self.BLOG_PATH)

    @property
    def RELEASES_URL(self) -> str:
        return urljoin(self.BASE_URL, self.RELEASES_PATH)


settings = Settings()
