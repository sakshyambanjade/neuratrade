from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from .models import Base
from config import DB_URL, SQLITE_BUSY_TIMEOUT_MS

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
