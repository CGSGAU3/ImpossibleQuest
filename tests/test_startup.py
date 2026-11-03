import subprocess
import sys


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

    assert "Каркас проекта установлен" in result.stdout
    assert "подключение к Telegram пока не добавлены" in result.stdout
    assert result.stderr == ""
