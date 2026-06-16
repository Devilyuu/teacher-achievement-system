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

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS annual_submissions (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    status VARCHAR(30) NOT NULL DEFAULT 'submitted',
                    submitted_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    CONSTRAINT uq_annual_submissions_user_year UNIQUE (user_id, year)
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_annual_submissions_user_id "
                "ON annual_submissions (user_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_annual_submissions_year "
                "ON annual_submissions (year)"
            )
        )
