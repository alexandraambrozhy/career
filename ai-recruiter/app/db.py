import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    requirements TEXT NOT NULL DEFAULT '',
    questions TEXT NOT NULL DEFAULT '[]',
    threshold INTEGER NOT NULL DEFAULT 70,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id),
    tg_user_id INTEGER,
    tg_username TEXT,
    name TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    answers TEXT NOT NULL DEFAULT '[]',
    resume_text TEXT NOT NULL DEFAULT '',
    resume_filename TEXT,
    score INTEGER,
    verdict TEXT,
    summary TEXT,
    strengths TEXT NOT NULL DEFAULT '[]',
    risks TEXT NOT NULL DEFAULT '[]',
    interview_questions TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paused_chats (
    business_connection_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (business_connection_id, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_candidates_tg_user ON candidates(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_candidates_vacancy ON candidates(vacancy_id, score DESC);
"""

STATUSES = {
    "new": "Новый",
    "shortlist": "Шорт-лист",
    "interview": "Интервью",
    "offer": "Оффер",
    "rejected": "Отказ",
}

_JSON_FIELDS = {"questions", "answers", "strengths", "risks", "interview_questions"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for key in _JSON_FIELDS & d.keys():
        d[key] = json.loads(d[key])
    return d


class Store:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- вакансии ---

    def create_vacancy(self, title: str, description: str, requirements: str,
                       questions: list[str], threshold: int = 70) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO vacancies (title, description, requirements, questions, threshold, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (title, description, requirements, json.dumps(questions, ensure_ascii=False),
                 threshold, _now()),
            )
            return cur.lastrowid

    def update_vacancy(self, vacancy_id: int, **fields) -> None:
        if "questions" in fields:
            fields["questions"] = json.dumps(fields["questions"], ensure_ascii=False)
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as c:
            c.execute(f"UPDATE vacancies SET {cols} WHERE id = ?", (*fields.values(), vacancy_id))

    def get_vacancy(self, vacancy_id: int) -> dict | None:
        with self._conn() as c:
            return _row(c.execute("SELECT * FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone())

    def list_vacancies(self, active_only: bool = False) -> list[dict]:
        sql = """
            SELECT v.*, COUNT(c.id) AS candidates_total,
                   SUM(CASE WHEN c.score >= v.threshold THEN 1 ELSE 0 END) AS candidates_fit
            FROM vacancies v LEFT JOIN candidates c ON c.vacancy_id = v.id
        """
        if active_only:
            sql += " WHERE v.active = 1"
        sql += " GROUP BY v.id ORDER BY v.id DESC"
        with self._conn() as c:
            return [_row(r) for r in c.execute(sql).fetchall()]

    # --- кандидаты ---

    def create_candidate(self, vacancy_id: int, **fields) -> int:
        fields = {"vacancy_id": vacancy_id, "created_at": _now(), **fields}
        for key in _JSON_FIELDS & fields.keys():
            fields[key] = json.dumps(fields[key], ensure_ascii=False)
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self._conn() as c:
            cur = c.execute(f"INSERT INTO candidates ({cols}) VALUES ({marks})", tuple(fields.values()))
            return cur.lastrowid

    def get_candidate(self, candidate_id: int) -> dict | None:
        with self._conn() as c:
            return _row(c.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone())

    def list_candidates(self, vacancy_id: int) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM candidates WHERE vacancy_id = ? ORDER BY score DESC NULLS LAST, id DESC",
                (vacancy_id,),
            ).fetchall()
            return [_row(r) for r in rows]

    def set_status(self, candidate_id: int, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        with self._conn() as c:
            c.execute("UPDATE candidates SET status = ? WHERE id = ?", (status, candidate_id))

    def has_applied(self, tg_user_id: int) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM candidates WHERE tg_user_id = ? LIMIT 1",
                             (tg_user_id,)).fetchone() is not None

    # --- чаты Telegram Business, где рекрутер отвечает сам ---

    def pause_chat(self, business_connection_id: str, chat_id: int) -> None:
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO paused_chats VALUES (?, ?, ?)",
                      (business_connection_id, chat_id, _now()))

    def is_paused(self, business_connection_id: str, chat_id: int) -> bool:
        with self._conn() as c:
            return c.execute(
                "SELECT 1 FROM paused_chats WHERE business_connection_id = ? AND chat_id = ?",
                (business_connection_id, chat_id),
            ).fetchone() is not None
