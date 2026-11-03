import subprocess
import sys

import pytest


def test_installed_package_starts_outside_project(tmp_path):
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "quest_bot"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    )

    assert "Карта загружена: сцен 151, концовок 38" in result.stdout
    assert "подключение к Telegram пока не добавлены" in result.stdout
    assert result.stderr == ""


def test_cli_accepts_external_map(tmp_path):
    path = tmp_path / "small.json"
    path.write_text(
        '{"start": 1, "secret_ending": 2, '
        '"1": {"type": "scene", "text": "Start", "choices": [{"text": "End", "next": 2}]}, '
        '"2": {"type": "ending", "text": "End", "choices": [], "ending_id": 1}}',
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "quest_bot", "--quest", str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    )

    assert "сцен 2, концовок 1" in result.stdout


@pytest.mark.parametrize("content", [None, "{", "{}"])
def test_bad_map_stops_startup_without_traceback(tmp_path, content):
    path = tmp_path / "bad.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "quest_bot", "--quest", str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )

    assert result.returncode != 0
    assert "Ошибка контента" in result.stderr
    assert str(path) in result.stderr
    assert "Traceback" not in result.stderr
    assert "Карта загружена" not in result.stdout
