"""
Точка запуска Virtual CEO.
Использование:
  python main.py          — запустить Telegram-бота
  python main.py --cli    — режим командной строки для тестирования
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()


def run_cli():
    from core.orchestrator import run
    history = []
    print("Virtual CEO CLI. Введите 'exit' для выхода.\n")
    while True:
        try:
            user_input = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            break
        if not user_input:
            continue
        if user_input.lower() == "exit":
            break
        response = run(user_input, history)
        print(f"\nСЕО: {response}\n")


def run_bot():
    from bot.telegram_bot import main
    main()


if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
    else:
        run_bot()
