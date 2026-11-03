import argparse
import sys

from .content import ContentError, load_content


def main():
    parser = argparse.ArgumentParser(description="Проверка карты Невозможного квеста")
    parser.add_argument("--quest", help="путь к другой карте в формате JSON")
    args = parser.parse_args()
    try:
        quest = load_content(args.quest)
    except ContentError as error:
        print(f"Ошибка контента: {error}", file=sys.stderr)
        return 1

    print(f"Карта загружена: сцен {len(quest.scenes)}, концовок {len(quest.endings)}.")
    print("Игровая логика и подключение к Telegram пока не добавлены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
