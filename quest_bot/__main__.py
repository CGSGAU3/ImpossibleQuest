import argparse
import asyncio
import sys

from .content import ContentError, load_content


def main():
    parser = argparse.ArgumentParser(description="Проверка карты Невозможного квеста")
    parser.add_argument("--quest", help="путь к другой карте в формате JSON")
    parser.add_argument("--serve", action="store_true", help="запустить бота с настройками окружения")
    args = parser.parse_args()
    if args.serve:
        from .bootstrap import serve
        try:
            asyncio.run(serve(args.quest))
        except (ContentError, ValueError, OSError) as error:
            print(f"Ошибка запуска: {error}", file=sys.stderr)
            return 1
        return 0
    try:
        quest = load_content(args.quest)
    except ContentError as error:
        print(f"Ошибка контента: {error}", file=sys.stderr)
        return 1

    print(f"Карта загружена: сцен {len(quest.scenes)}, концовок {len(quest.endings)}.")
    print("Для запуска Telegram-бота используй --serve. Нужны настройки окружения.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
