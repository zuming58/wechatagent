from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def ensure_messages_fts(connection) -> None:
    connection.execute(text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            message_id UNINDEXED,
            account_id UNINDEXED,
            conversation_id UNINDEXED,
            text_content,
            tokenize = 'trigram'
        )
    """))


def ensure_legacy_contact_profile_columns(connection) -> None:
    """Repair databases created before profile overrides were versioned."""
    if connection.dialect.name != "sqlite":
        return
    columns = {row["name"] for row in connection.execute(text("PRAGMA table_info(contacts)")).mappings()}
    for column in (
        "user_remark_name",
        "user_confirmed_real_name",
        "user_company",
        "user_role",
    ):
        if column not in columns:
            connection.execute(text(f"ALTER TABLE contacts ADD COLUMN {column} VARCHAR(255)"))


def alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parent.parent
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def supports_alembic(target_engine: Engine) -> bool:
    return not (target_engine.url.drivername.startswith("sqlite") and target_engine.url.database is None)


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def initialize_database(target_engine: Engine | None = None) -> None:
    from . import models  # noqa: F401

    current_engine = target_engine or engine
    database_url = str(current_engine.url)
    has_version_table = inspect(current_engine).has_table("alembic_version")
    if has_version_table and supports_alembic(current_engine):
        command.upgrade(alembic_config(database_url), "head")
    Base.metadata.create_all(current_engine)
    with current_engine.begin() as connection:
        ensure_legacy_contact_profile_columns(connection)
        ensure_messages_fts(connection)
    if not has_version_table and supports_alembic(current_engine):
        command.stamp(alembic_config(database_url), "head")


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
