from typing import Optional, Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, func, Integer

class Base(DeclarativeBase):
    pass

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