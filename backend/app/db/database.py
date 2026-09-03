from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine: Engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    future=True
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def configure_database(custom_settings: Settings) -> None:
    global engine, SessionLocal

    engine = create_engine(
        custom_settings.database_url,
        connect_args={"check_same_thread": False},
        future=True
    )
    SessionLocal.configure(bind=engine)


def init_db() -> None:
    from backend.app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_accounts_table()


def migrate_accounts_table() -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("accounts")}

    statements: list[str] = []
    if "access_token" not in columns:
        statements.append("ALTER TABLE accounts ADD COLUMN access_token TEXT")
    if "access_token_expires_at" not in columns:
        statements.append("ALTER TABLE accounts ADD COLUMN access_token_expires_at DATETIME")
    if "account_status" not in columns:
        statements.append("ALTER TABLE accounts ADD COLUMN account_status VARCHAR(24) DEFAULT 'disconnected'")

    if not statements:
        if "account_status" in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE accounts
                        SET account_status = CASE
                            WHEN last_test_status = 'success' THEN 'connected'
                            ELSE 'disconnected'
                        END
                        WHERE account_status IS NULL OR account_status = ''
                        """
                    )
                )
        migrate_accounts_nurture()
        migrate_app_settings()
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                """
                UPDATE accounts
                SET account_status = CASE
                    WHEN last_test_status = 'success' THEN 'connected'
                    ELSE 'disconnected'
                END
                WHERE account_status IS NULL OR account_status = ''
                """
            )
        )
    migrate_accounts_nurture()
    migrate_app_settings()


def migrate_accounts_nurture() -> None:
    inspector = inspect(engine)
    try:
        cols = {column["name"] for column in inspector.get_columns("accounts")}
        stmts = []
        for col in ("nurture_stage", "nurture_next_at", "nurture_count", "nurture_status"):
            if col not in cols:
                if col in ("nurture_stage", "nurture_count"):
                    stmts.append(f"ALTER TABLE accounts ADD COLUMN {col} INTEGER DEFAULT 0")
                elif col == "nurture_next_at":
                    stmts.append(f"ALTER TABLE accounts ADD COLUMN {col} DATETIME")
                else:
                    stmts.append(f"ALTER TABLE accounts ADD COLUMN {col} VARCHAR(16) DEFAULT 'pending'")
        if stmts:
            with engine.begin() as conn:
                for s in stmts:
                    conn.execute(text(s))
    except Exception:
        pass


def migrate_app_settings() -> None:
    inspector = inspect(engine)
    try:
        cols = {column["name"] for column in inspector.get_columns("app_settings")}
        stmts = []
        for col in ("sms_provider", "sms_api_key", "sms_country", "sms_operator"):
            if col not in cols:
                stmts.append(f"ALTER TABLE app_settings ADD COLUMN {col} TEXT DEFAULT ''")
        if stmts:
            with engine.begin() as conn:
                for s in stmts:
                    conn.execute(text(s))
    except Exception:
        pass


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
