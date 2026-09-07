#!/usr/bin/env python3
"""Online local-stack backup; never prints credentials or restarts services."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-p", "project_monitor", "-f", str(ROOT / "docker-compose.yml")]


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def capture(args, destination):
    with destination.open("wb") as stream:
        run(args, stdout=stream)


def main():
    os.umask(0o077)
    parent = ROOT / "backups"
    parent.mkdir(exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = Path(tempfile.mkdtemp(prefix=stamp + "-", dir=parent))
    containers = {}
    for service in ("postgres", "n8n", "monitoring-agent"):
        value = run(COMPOSE + ["ps", "-q", service], capture_output=True, text=True).stdout.strip()
        if not value:
            raise RuntimeError(f"{service} must be running for online backup")
        containers[service] = value
    pg = containers["postgres"]
    n8n = containers["n8n"]
    capture(["docker", "exec", pg, "sh", "-c",
             'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges'],
            dest / "postgres.dump")
    with (dest / "postgres.dump").open("rb") as stream:
        run(["docker", "exec", "-i", pg, "pg_restore", "--list"], stdin=stream, stdout=subprocess.DEVNULL)

    temporary = "/tmp/project-monitor-backup-" + uuid.uuid4().hex + ".sqlite"
    javascript = '''const {DatabaseSync,backup}=require("node:sqlite");
const db=new DatabaseSync("/home/node/.n8n/database.sqlite",{readOnly:true});
backup(db,process.argv[1]).then(()=>db.close()).catch(e=>{console.error(e.message);process.exitCode=1;});'''
    try:
        run(["docker", "exec", n8n, "node", "-e", javascript, temporary])
        run(["docker", "cp", n8n + ":" + temporary, str(dest / "n8n.sqlite")], stdout=subprocess.DEVNULL)
    finally:
        run(["docker", "exec", n8n, "node", "-e",
             'require("fs").rmSync(process.argv[1],{force:true})', temporary])
    with sqlite3.connect((dest / "n8n.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("n8n SQLite integrity check failed")
    # Include n8n's generated encryption key, binary data, and custom nodes.
    capture(["docker", "exec", n8n, "tar", "czf", "-", "-C", "/home/node/.n8n",
             "--exclude=database.sqlite", "--exclude=database.sqlite-wal", "--exclude=database.sqlite-shm", "."],
            dest / "n8n-files.tar.gz")
    capture(["docker", "exec", containers["monitoring-agent"], "tar", "czf", "-", "-C", "/app/backups", "."],
            dest / "remediation-backups.tar.gz")
    for name in (".env", "docker-compose.yml"):
        if (ROOT / name).exists():
            shutil.copyfile(ROOT / name, dest / name)
    hashes = {}
    for path in dest.iterdir():
        if path.is_file():
            with path.open("rb") as stream:
                hashes[path.name] = hashlib.file_digest(stream, "sha256").hexdigest()
    (dest / "manifest.json").write_text(json.dumps({"created_utc": stamp, "sha256": hashes}, indent=2) + "\n")
    (dest / "COMPLETE").write_text("PostgreSQL archive listing and SQLite integrity verified.\n")
    print(f"Backup completed: {dest}")
    print("Contains secrets. Keep private and copy to separate storage. No automatic deletion is configured.")


if __name__ == "__main__":
    main()
