"""CLI smoke tests (CLID-01, CLID-02)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import app_cli

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_start_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app_cli, ["start", "--help"])
    assert result.exit_code == 0
    out = (result.stdout or "").lower()
    assert "polarprocess" in out or "lifecycle" in out


def test_start_delegates_to_exact_polarprocess_service(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True, "pid": 12345}

    def fake_get(url: str, **_: object) -> Response:
        calls.append(("GET", url))
        return Response()

    def fake_post(url: str, **_: object) -> Response:
        calls.append(("POST", url))
        return Response()

    monkeypatch.setattr("app.cli.httpx.get", fake_get)
    monkeypatch.setattr("app.cli.httpx.post", fake_post)

    result = CliRunner().invoke(app_cli, ["start"])

    assert result.exit_code == 0, result.output
    assert calls == [
        ("GET", "http://127.0.0.1:11055/api/health"),
        ("POST", "http://127.0.0.1:11055/api/services/privportal-backend/start"),
    ]


def test_init_db_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "init_mig.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("PRIVPORTAL_DATABASE_URL", url)
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "init-db"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_import_demo_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "demo.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("PRIVPORTAL_MASTER_PASSWORD", "pytest-demo-mpw-999")
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "import-demo", "--database-url", url],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert db_file.exists()
    conn = sqlite3.connect(db_file)
    try:
        row = conn.execute("SELECT COUNT(*) FROM projects").fetchone()
        assert row is not None and row[0] >= 1
    finally:
        conn.close()


def test_privportal_test_command() -> None:
    """CLI `test` runs pytest subprocess (collect-only keeps CI fast)."""
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "test", "--", "--collect-only"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_serve_command_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app_cli, ["serve", "--help"])
    assert result.exit_code == 0, result.output
    out = (result.stdout or "").lower()
    assert "uvicorn" in out or "standalone" in out or "localhost" in out


def test_serve_runs_uvicorn_on_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(app: str, **kwargs: object) -> None:
        calls.append({"app": app, **kwargs})

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = CliRunner().invoke(app_cli, ["serve"])

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0]["app"] == "app.main:app"
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 12790
