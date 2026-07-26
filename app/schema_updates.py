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
        if "last_login_at" not in columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN last_login_at DATETIME")
            )

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_reporting_years (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    is_default BOOLEAN NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                    CONSTRAINT uq_user_reporting_years_user_year
                        UNIQUE (user_id, year)
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_reporting_years_user_id "
                "ON user_reporting_years (user_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_reporting_years_year "
                "ON user_reporting_years (year)"
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
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS trial_feedback (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    issue_type VARCHAR(40) NOT NULL DEFAULT '其他',
                    current_page VARCHAR(255) NOT NULL DEFAULT '',
                    related_title VARCHAR(255) NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    status VARCHAR(30) NOT NULL DEFAULT '待处理',
                    admin_note TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_trial_feedback_user_id "
                "ON trial_feedback (user_id)"
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS feishu_sync_records (
                    id INTEGER NOT NULL PRIMARY KEY,
                    achievement_id INTEGER NOT NULL,
                    feishu_record_id VARCHAR(255),
                    sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    last_synced_at DATETIME,
                    last_error TEXT NOT NULL DEFAULT '',
                    payload_hash VARCHAR(64) NOT NULL DEFAULT '',
                    sync_claim_token VARCHAR(64),
                    create_client_token VARCHAR(36),
                    create_client_token_payload_hash VARCHAR(64),
                    create_payload_json TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(achievement_id)
                        REFERENCES achievements (id) ON DELETE CASCADE,
                    CONSTRAINT ck_feishu_sync_records_status
                        CHECK (
                            sync_status IN (
                                'pending',
                                'synced',
                                'failed',
                                'conflict'
                            )
                        )
                )
                """
            )
        )
        sync_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(feishu_sync_records)")
            )
        }
        if "sync_claim_token" not in sync_columns:
            connection.execute(
                text(
                    "ALTER TABLE feishu_sync_records "
                    "ADD COLUMN sync_claim_token VARCHAR(64)"
                )
            )
        if "create_client_token" not in sync_columns:
            connection.execute(
                text(
                    "ALTER TABLE feishu_sync_records "
                    "ADD COLUMN create_client_token VARCHAR(36)"
                )
            )
        if "create_client_token_payload_hash" not in sync_columns:
            connection.execute(
                text(
                    "ALTER TABLE feishu_sync_records "
                    "ADD COLUMN create_client_token_payload_hash VARCHAR(64)"
                )
            )
        if "create_payload_json" not in sync_columns:
            connection.execute(
                text(
                    "ALTER TABLE feishu_sync_records "
                    "ADD COLUMN create_payload_json TEXT"
                )
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_feishu_sync_records_achievement_id "
                "ON feishu_sync_records (achievement_id)"
            )
        )
