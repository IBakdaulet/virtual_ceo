"""
Virtual CEO — главный оркестратор.
Принимает запрос от пользователя, определяет нужного агента и возвращает ответ.
"""

import anthropic
import os
from typing import Optional

SYSTEM_PROMPT = """Ты — Виртуальный СЕО медиа-холдинга. Твой владелец — Ибакдаулет, казахстанский медиа-предприниматель.

У тебя есть несколько специализированных агентов в подчинении:
- content — генерация контента для Grants KZ и Ekonomist Media
- grants — поиск актуальных грантов/стипендий и подготовка постов (реальный парсинг сайтов)
- finance — личные финансы: состояние счетов, анализ расходов, финансовые цели, рекомендации
- sales — помощь отделу продаж
- hr — подбор сотрудников и скрининг

Проекты владельца:
- Kettik Group — медиа-холдинг (~75M тенге/мес), роль стратегическая
- Tanda Bilim — история Казахстана (видеоконтент, ~1.5M тенге/мес)
- Grants KZ — гранты за рубежом (~1.5M тенге/мес)
- Ekonomist Media — экономика/финансы (молодой, пока не зарабатывает)

Твоя задача:
1. Понять что хочет владелец
2. Если задача относится к агенту — вызвать его через инструмент route_to_agent
3. Если можешь ответить сам — отвечай кратко и по делу
4. Общайся на русском языке

ВАЖНО: Когда агент возвращает готовый контент (пост, текст, сценарий) — передавай его владельцу ПОЛНОСТЬЮ без изменений. Не делай резюме, не пересказывай. Просто верни весь текст что вернул агент."""

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def route_to_agent(agent_name: str, task: str) -> str:
    """Вызов специализированного агента."""
    from agents.content_agent import ContentAgent
    from agents.grants_agent import GrantsAgent
    from agents.finance_agent import FinanceAgent
    from agents.sales_agent import SalesAgent

    agents = {
        "content": ContentAgent(),
        "grants": GrantsAgent(),
        "finance": FinanceAgent(),
        "sales": SalesAgent(),
    }

    if agent_name in agents:
        return agents[agent_name].run(task)
    return f"Агент '{agent_name}' ещё не подключён."


tools = [
    {
        "name": "route_to_agent",
        "description": "Передать задачу специализированному агенту",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "enum": ["content", "grants", "finance", "sales", "hr"],
                    "description": "Имя агента"
                },
                "task": {
                    "type": "string",
                    "description": "Описание задачи для агента"
                }
            },
            "required": ["agent_name", "task"]
        }
    }
]


def run(user_message: str, history: Optional[list] = None) -> str:
    """
    Главная точка входа. Принимает сообщение, возвращает ответ.
    history — список предыдущих сообщений для поддержки контекста.
    """
    messages = history or []
    messages.append({"role": "user", "content": user_message})

    while True:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages
        )

        # Нет вызова инструмента — возвращаем текст
        if response.stop_reason == "end_turn":
            text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                ""
            )
            messages.append({"role": "assistant", "content": response.content})
            return text

        # Есть вызов инструмента
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = route_to_agent(
                        block.input["agent_name"],
                        block.input["task"]
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Непредвиденный stop_reason
        break

    return "Не удалось получить ответ."
