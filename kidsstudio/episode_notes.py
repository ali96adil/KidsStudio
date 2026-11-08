"""Local-only, append-only episode notes for supervised owner review.

Separate SQLite database; never writes to StudioQueue or YouTube.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Iterator

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


def _validate_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("invalid episode id")
    return value


class EpisodeNotes:
    def __init__(self, database: str | Path):
        self.path = Path(database).expanduser().resolve()
        if self.path.suffix not in {".db", ".sqlite"}:
            raise ValueError("invalid notes database")
        if any((p / ".git").exists() for p in (self.path.parent, *self.path.parents)):
            raise ValueError("notes must remain outside Git")

    def initialize(self) -> None:
        if self.path.exists():
            raise FileExistsError("notes database already exists")
        if not self.path.parent.is_dir() or self.path.parent.stat().st_mode & 0o077:
            raise ValueError("private existing parent directory required")
        import os
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with self._connection() as db:
                db.executescript("""
                    CREATE TABLE notes (
                        note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        episode_id TEXT NOT NULL,
                        event_type TEXT NOT NULL CHECK(event_type IN ('ADD','RESOLVE')),
                        note_text TEXT NOT NULL,
                        target_note_id INTEGER,
                        created_at REAL NOT NULL
                    );
                    CREATE INDEX notes_episode ON notes(episode_id,note_id);
                """)
        except Exception:
            self.path.unlink(missing_ok=True)
            raise

    def _connect(self, *, readonly: bool = False):
        if not self.path.is_file():
            raise ValueError("notes database not initialized")
        if readonly:
            return sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        return sqlite3.connect(self.path)

    @contextmanager
    def _connection(self, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
        """Commit or roll back as before, then always release the file handle."""
        db = self._connect(readonly=readonly)
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, *, episode_id: str, text: str) -> int:
        _validate_id(episode_id)
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("invalid note text")
        with self._connection() as db:
            cur = db.execute(
                "INSERT INTO notes(episode_id,event_type,note_text,target_note_id,created_at) "
                "VALUES(?,'ADD',?,NULL,?)",
                (episode_id, text.strip(), time.time()),
            )
            return int(cur.lastrowid)

    def resolve(self, *, episode_id: str, note_id: int) -> int:
        _validate_id(episode_id)
        if type(note_id) is not int or note_id <= 0:
            raise ValueError("invalid note id")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT note_id FROM notes WHERE note_id=? AND episode_id=? "
                "AND event_type='ADD'", (note_id, episode_id)
            ).fetchone()
            if row is None:
                raise ValueError("note not found")
            if db.execute(
                "SELECT 1 FROM notes WHERE episode_id=? AND event_type='RESOLVE' "
                "AND target_note_id=?", (episode_id, note_id)
            ).fetchone():
                raise ValueError("note already resolved")
            cur = db.execute(
                "INSERT INTO notes(episode_id,event_type,note_text,target_note_id,created_at) "
                "VALUES(?,'RESOLVE','',?,?)",
                (episode_id, note_id, time.time()),
            )
            return int(cur.lastrowid)

    def list_notes(self, *, episode_id: str) -> list[dict]:
        _validate_id(episode_id)
        with self._connection(readonly=True) as db:
            rows = db.execute(
                "SELECT note_id,event_type,note_text,target_note_id FROM notes "
                "WHERE episode_id=? ORDER BY note_id", (episode_id,)
            ).fetchall()
        resolved = {target for _, typ, _, target in rows if typ == "RESOLVE"}
        return [{"note_id": note_id, "text": text, "resolved": note_id in resolved}
                for note_id, typ, text, _ in rows if typ == "ADD"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local private episode review notes")
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    add = sub.add_parser("add")
    add.add_argument("--episode-id", required=True)
    add.add_argument("--text", required=True)
    resolve = sub.add_parser("resolve")
    resolve.add_argument("--episode-id", required=True)
    resolve.add_argument("--note-id", type=int, required=True)
    show = sub.add_parser("list")
    show.add_argument("--episode-id", required=True)
    args = parser.parse_args(argv)
    try:
        notes = EpisodeNotes(args.db)
        if args.action == "init":
            notes.initialize()
            result = {"status": "INITIALIZED"}
        elif args.action == "add":
            result = {"status": "NOTE_ADDED", "note_id": notes.add(
                episode_id=args.episode_id, text=args.text)}
        elif args.action == "resolve":
            result = {"status": "NOTE_RESOLVED", "event_id": notes.resolve(
                episode_id=args.episode_id, note_id=args.note_id)}
        else:
            result = {"status": "NOTES", "notes": notes.list_notes(
                episode_id=args.episode_id)}
    except (ValueError, OSError, sqlite3.Error):
        print(json.dumps({"status": "NOTES_ERROR", "publication_approved": False}))
        return 2
    result["publication_approved"] = False
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
