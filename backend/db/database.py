from config import DB_URL, SQLITE_BUSY_TIMEOUT_MS
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .models import Base

engine = create_engine(
    DB_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000.0,
    },
    future=True,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS};")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_research_metadata_columns()


def _ensure_research_metadata_columns():
    columns_by_table = {
        "model_runs": {
            "prompt_version": "VARCHAR DEFAULT 'v1' NOT NULL",
            "system_prompt_hash": "VARCHAR DEFAULT '' NOT NULL",
            "temperature": "FLOAT DEFAULT 0.0 NOT NULL",
            "ollama_model_tag": "VARCHAR DEFAULT '' NOT NULL",
            "hardware_tag": "VARCHAR DEFAULT '' NOT NULL",
        },
        "inference_logs": {
            "prompt_version": "VARCHAR DEFAULT 'v1' NOT NULL",
            "system_prompt_hash": "VARCHAR DEFAULT '' NOT NULL",
            "temperature": "FLOAT DEFAULT 0.0 NOT NULL",
            "ollama_model_tag": "VARCHAR DEFAULT '' NOT NULL",
            "hardware_tag": "VARCHAR DEFAULT '' NOT NULL",
            "market_tick_id": "INTEGER",
            "cycle_indicator_id": "INTEGER",
            "prompt_template_id": "INTEGER",
            "rendered_prompt": "TEXT DEFAULT '' NOT NULL",
            "data_quality": "VARCHAR DEFAULT 'valid' NOT NULL",
        },
        "metric_snapshots": {
            "data_gap": "BOOLEAN DEFAULT 0 NOT NULL",
        },
    }
    with engine.begin() as connection:
        for table, columns in columns_by_table.items():
            existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
            for column, definition in columns.items():
                if column not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
