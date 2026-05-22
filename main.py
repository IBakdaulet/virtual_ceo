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


def sync_data_from_github():
    """Скачивает актуальные data-файлы из GitHub при старте."""
    import base64, httpx, json
    from pathlib import Path
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return
    files = ["data/finance.json", "data/historical_sales.json", "data/sales.json"]
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    for repo_path in files:
        try:
            url = f"https://api.github.com/repos/IBakdaulet/virtual_ceo/contents/{repo_path}"
            resp = httpx.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                content = base64.b64decode(resp.json()["content"]).decode()
                local_path = Path(__file__).parent / repo_path
                local_path.parent.mkdir(exist_ok=True)
                local_path.write_text(content, encoding="utf-8")
                print(f"✅ Синхронизирован: {repo_path}")
        except Exception as e:
            print(f"⚠️ Не удалось синхронизировать {repo_path}: {e}")


def run_bot():
    sync_data_from_github()
    from bot.telegram_bot import main
    main()


if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
    else:
        run_bot()
