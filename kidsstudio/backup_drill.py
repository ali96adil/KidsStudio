"""M9 offline SQLite backup and sacrificial restore drill for Studio Brain.

Uses SQLite's online consistent backup API. Never overwrites or restores into
the active database, never runs a database migration, and never writes backup
bytes into Git. Backup files may contain sensitive worker data: store privately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any

from .episode_assembly import digest, _ensure_private


class BackupError(ValueError):
    """Studio Brain backup/restore verification blocked."""


def _file_path(path: str | Path, *, must_exist: bool) -> Path:
    p=Path(path).expanduser()
    if not p.is_absolute() or p.is_symlink():
        raise BackupError("Use an explicit absolute non-symlink file path.")
    p=p.resolve()
    _ensure_private(p.parent)
    if must_exist and (not p.is_file() or p.stat().st_size<=0):
        raise BackupError("Required private SQLite file is missing or empty.")
    if p.suffix not in (".sqlite",".db"):
        raise BackupError("Backup must have .sqlite or .db extension.")
    return p


def _integrity(db: sqlite3.Connection) -> dict[str, Any]:
    rows=db.execute("PRAGMA integrity_check").fetchall()
    if rows != [("ok",)]:
        raise BackupError("SQLite integrity_check found corruption.")
    foreign=db.execute("PRAGMA foreign_key_check").fetchall()
    if foreign:
        raise BackupError("SQLite foreign_key_check found invalid references.")
    tables=[x[0] for x in db.execute("""
        SELECT name FROM sqlite_master WHERE type='table'
          AND name NOT LIKE 'sqlite_%' ORDER BY name""")]
    if "jobs" not in tables or "settings" not in tables:
        raise BackupError("Not a Studio Brain queue database.")
    sizes={}
    for table in tables:
        safe='"'+table.replace('"','""')+'"'
        sizes[table]=db.execute("SELECT COUNT(*) FROM "+safe).fetchone()[0]
    return {"table_count":len(tables),"table_rows":sizes,
            "integrity_check":"ok","foreign_key_check":"ok"}


def create_backup(source: str | Path, destination: str | Path) -> dict[str, Any]:
    src=_file_path(source,must_exist=True)
    dst=_file_path(destination,must_exist=False)
    if src==dst or dst.exists() or dst.is_symlink():
        raise BackupError("Backup location exists, is unsafe or equals source.")
    if not dst.parent.is_dir():
        raise BackupError("Create private backup folder deliberately before backup.")
    fd=os.open(str(dst),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    os.close(fd)
    try:
        # A SQLite online backup captures one consistent DB snapshot even with WAL.
        origin=sqlite3.connect("file:"+str(src)+"?mode=ro",uri=True,timeout=5)
        dest=sqlite3.connect(dst,timeout=5)
        try:
            origin.execute("PRAGMA busy_timeout=5000")
            origin.backup(dest,pages=32,sleep=0.1)
            dest.commit()
            proof=_integrity(dest)
        finally:
            dest.close()
            origin.close()
        os.chmod(dst,0o600)
        return {"status":"BACKUP_VERIFIED_NOT_RESTORED_TO_PRODUCTION",
                "backup_sha256":digest(dst),
                "backup_bytes":dst.stat().st_size,
                **proof,"production_changed":False}
    except BaseException:
        # Quarantine the partial file; never delete or overwrite silently.
        raise


def restore_drill(source_backup: str | Path) -> dict[str, Any]:
    """Read a private backup, restore only into a NEW throwaway temp DB."""
    backup=_file_path(source_backup,must_exist=True)
    original_sha=digest(backup)
    original_size=backup.stat().st_size
    with tempfile.TemporaryDirectory(prefix="kidsstudio-restore-drill-") as td:
        restored=Path(td)/"restored.sqlite"
        origin=sqlite3.connect("file:"+str(backup)+"?mode=ro",uri=True,timeout=5)
        target=sqlite3.connect(restored,timeout=5)
        try:
            baseline=_integrity(origin)
            origin.backup(target,pages=32,sleep=0.1)
            target.commit()
            proof=_integrity(target)
            if proof!=baseline:
                raise BackupError("Restored database tables do not match backup snapshot.")
        finally:
            target.close()
            origin.close()
        if digest(backup)!=original_sha or backup.stat().st_size!=original_size:
            raise BackupError("Backup changed while restoring.")
        return {"status":"SACRIFICIAL_RESTORE_DRILL_PASSED",
                "source_backup_sha256":original_sha,
                "restored_to_production":False,
                "restored_table_count":proof["table_count"],
                "restored_row_counts":proof["table_rows"],
                "integrity_check":"ok","foreign_key_check":"ok"}


def main(argv=None) -> int:
    p=argparse.ArgumentParser(prog="studio-backup-drill")
    x=p.add_mutually_exclusive_group(required=True)
    x.add_argument("--source",type=Path)
    x.add_argument("--restore-drill",type=Path)
    p.add_argument("--destination",type=Path)
    args=p.parse_args(argv)
    if bool(args.source)!=bool(args.destination):
        p.error("--source and --destination must be provided together.")
    try:
        result=(create_backup(args.source,args.destination)
                if args.source else restore_drill(args.restore_drill))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (BackupError,sqlite3.DatabaseError,OSError,ValueError) as exc:
        print("STUDIO_BACKUP_ERROR: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
