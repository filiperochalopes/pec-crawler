from typing import Optional, Any, Dict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, JSON, func, Integer

class Base(DeclarativeBase):
    pass

class CrawlerRun(Base):
    __tablename__ = "crawler_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    versao_label: Mapped[Optional[str]] = mapped_column(String(32))
    url_release_page: Mapped[Optional[str]] = mapped_column(Text)
    link_linux: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(64))
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)  # dados completos da extração
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class PecVersion(Base):
    __tablename__ = "pec_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    download_link: Mapped[str] = mapped_column(Text, nullable=False)
    release_notes_page: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    release_notes_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # TIMESTAMP (sem timezone) conforme DDL; default no servidor
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<PecVersion id={self.id} version={self.version}>"