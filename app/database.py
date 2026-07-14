import os
import stat
import logging
from sqlmodel import SQLModel, create_engine
from sqlalchemy import event, text

logger = logging.getLogger(__name__)

DB_PATH = "./brambet.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA secure_delete=ON")
    cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")
    cursor.close()


def _add_column_if_missing(engine, table: str, column: str, col_type: str):
    """Add a column to a table if it doesn't already exist (SQLite ALTER TABLE)."""
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in result}
        if column not in existing:
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            )
            conn.commit()
            logger.info(f"Migrated: added column {column} to {table}")


def create_db():
    SQLModel.metadata.create_all(engine)

    _add_column_if_missing(engine, "job", "is_short", "BOOLEAN DEFAULT 0")
    _add_column_if_missing(engine, "job", "duration_seconds", "INTEGER DEFAULT 0")
    _add_column_if_missing(engine, "job", "video_type", "VARCHAR DEFAULT ''")

    if os.path.exists(DB_PATH):
        os.chmod(DB_PATH, stat.S_IRUSR | stat.S_IWUSR)
    logger.info("Database created and secured")
