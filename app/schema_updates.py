from sqlalchemy import text

from app.database import engine


def apply_schema_updates() -> None:
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(users)"))
        }
        if "must_change_password" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"
                )
            )
