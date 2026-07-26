from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_PATH


DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def configure_sqlite_engine(database_engine: Engine) -> Engine:
    if (
        database_engine.dialect.name == "sqlite"
        and not event.contains(
            database_engine,
            "connect",
            _enable_sqlite_foreign_keys,
        )
    ):
        event.listen(
            database_engine,
            "connect",
            _enable_sqlite_foreign_keys,
        )
    return database_engine


engine = configure_sqlite_engine(
    create_engine(
        f"sqlite:///{DATABASE_PATH}",
        connect_args={"check_same_thread": False},
    )
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
