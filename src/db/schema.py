"""Database schema initialization."""

from sqlalchemy import text

from src.db.session import create_db_session


def init_schema() -> None:
    statements = [
        """CREATE TABLE IF NOT EXISTS investigations (
            investigation_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            tags TEXT,
            live_source_enabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS investigation_files (
            file_id TEXT PRIMARY KEY,
            investigation_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            content_type TEXT,
            size_bytes INTEGER,
            row_count INTEGER,
            columns_json TEXT,
            created_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS chat_messages (
            message_id TEXT PRIMARY KEY,
            investigation_id TEXT NOT NULL,
            run_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            citations TEXT,
            created_at TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_inv_files_investigation_id ON investigation_files(investigation_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_investigation_id ON chat_messages(investigation_id)",
        """CREATE TABLE IF NOT EXISTS audit_events (
            audit_id TEXT PRIMARY KEY,
            investigation_id TEXT,
            run_id TEXT,
            actor_user_id TEXT NOT NULL,
            actor_unit TEXT,
            actor_rank TEXT,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            source TEXT,
            sql TEXT,
            row_count INTEGER,
            latency_ms INTEGER,
            error_message TEXT,
            payload TEXT,
            created_at TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_audit_investigation_id ON audit_events(investigation_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_run_id ON audit_events(run_id)",
        """CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            input_text TEXT NOT NULL,
            instruction TEXT NOT NULL,
            output_text TEXT,
            provider TEXT,
            model TEXT,
            error_message TEXT,
            created_at TEXT,
            updated_at TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)",
    ]
    with create_db_session() as session:
        for stmt in statements:
            session.execute(text(stmt))
        session.commit()
