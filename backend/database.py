"""SQLite storage for the history viewer and the explanation cache."""
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path


class Database:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self._create_table()

    def _connect(self) -> sqlite3.Connection:
        # A new connection per call keeps things thread-safe and simple;
        # SQLite connections are cheap for a small local file.
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row  # lets us read columns by name
        return connection

    def _create_table(self) -> None:
        # `with closing(...)` closes the connection; `with connection` commits.
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at  TEXT NOT NULL,
                    mode        TEXT NOT NULL,
                    snippet     TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    model       TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def save(self, snippet: str, mode: str, explanation: str, model: str = "") -> None:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO history (created_at, mode, snippet, explanation, model) "
                "VALUES (?, ?, ?, ?, ?)",
                (created_at, mode, snippet, explanation, model),
            )

    def find_cached(self, snippet: str, mode: str):
        """Return the newest saved explanation for this snippet+mode, or None."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT explanation FROM history WHERE snippet = ? AND mode = ? "
                "ORDER BY id DESC LIMIT 1",
                (snippet, mode),
            ).fetchone()
        return row["explanation"] if row else None

    def search(self, query: str = "", limit: int = 200) -> list:
        """Newest-first rows whose snippet or explanation contains `query`."""
        pattern = f"%{query.strip()}%"
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT * FROM history WHERE snippet LIKE ? OR explanation LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (pattern, pattern, limit),
            ).fetchall()


if __name__ == "__main__":
    # Quick self-test:  python -m backend.database   (uses a throwaway file)
    test_db = Database("test_history.db")
    test_db.save("print('hi')", "Explain", "Prints hi.", "demo-model")
    print("Cached:", test_db.find_cached("print('hi')", "Explain"))
    print("Search 'hi':", [dict(row) for row in test_db.search("hi")])
    Path("test_history.db").unlink()