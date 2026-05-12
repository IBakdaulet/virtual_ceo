"""
Grants Agent — поиск грантов и подготовка постов для Grants KZ.
Использует парсеры из edu-news-bot + Claude для генерации поста.
"""

import asyncio
import anthropic
import os
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PARSERS = [
    ("agents.grants_scraper.parsers.bolashak_parser", "BolashakParser"),
    ("agents.grants_scraper.parsers.studyqa_parser", "StudyQAParser"),
    ("agents.grants_scraper.parsers.topuniversities_parser", "TopUniversitiesParser"),
    ("agents.grants_scraper.parsers.globalscholarships_parser", "GlobalScholarshipsParser"),
    ("agents.grants_scraper.parsers.opportunitiescircle_parser", "OpportunitiesCircleParser"),
]


async def _fetch_from_parser(module_name: str, class_name: str) -> List[Dict]:
    """Загружает статьи из одного парсера."""
    try:
        import importlib
        module = importlib.import_module(module_name)
        ParserClass = getattr(module, class_name)
        parser = ParserClass()
        articles = await parser.fetch_articles()
        return articles or []
    except Exception as e:
        logger.warning(f"Парсер {class_name} ошибка: {e}")
        return []


async def search_grants(query: str = "", limit: int = 5) -> List[Dict]:
    """Ищет актуальные гранты через все парсеры."""
    tasks = [_fetch_from_parser(m, c) for m, c in PARSERS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles = []
    for result in results:
        if isinstance(result, list):
            all_articles.extend(result)

    # Фильтрация по запросу если задан
    if query:
        query_lower = query.lower()
        filtered = [
            a for a in all_articles
            if query_lower in (a.get("title") or "").lower()
            or query_lower in (a.get("content") or "").lower()
        ]
        all_articles = filtered if filtered else all_articles

    return all_articles[:limit]


def generate_post(articles: List[Dict], project: str = "Grants KZ") -> str:
    """Генерирует готовый пост на основе найденных статей через Claude."""
    if not articles:
        return "Не удалось найти актуальные гранты по вашему запросу."

    articles_text = ""
    for i, a in enumerate(articles, 1):
        title = a.get("title") or "Без названия"
        url = a.get("url") or ""
        content = (a.get("content") or "")[:500]
        articles_text += f"\n{i}. {title}\nСсылка: {url}\n{content}\n"

    prompt = f"""На основе этих материалов о грантах подготовь готовый пост для Instagram/Telegram канала {project}.

Материалы:
{articles_text}

Требования к посту:
- 150-250 слов
- Живой, вдохновляющий тон для казахстанской молодёжи 18-28 лет
- Конкретные факты (дедлайны, суммы, условия если есть)
- Призыв к действию в конце
- 5-7 релевантных хэштегов
- Язык: русский"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


class GrantsAgent:
    def run(self, task: str) -> str:
        """Синхронная обёртка для вызова из оркестратора."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self._run_async(task))
                    return future.result()
            return loop.run_until_complete(self._run_async(task))
        except Exception:
            return asyncio.run(self._run_async(task))

    async def _run_async(self, task: str) -> str:
        articles = await search_grants(query=task, limit=5)
        if not articles:
            # Если парсеры не дали результат — генерируем пост только через Claude
            return self._generate_post_from_query(task)
        return generate_post(articles)

    def _generate_post_from_query(self, task: str) -> str:
        """Генерирует пост через Claude без скрапинга (fallback)."""
        prompt = f"""Подготовь готовый пост для Instagram/Telegram канала Grants KZ на тему: {task}

Grants KZ — казахстанское медиа о зарубежных грантах и стипендиях.
Аудитория: молодёжь 18-28 лет, хотят учиться за рубежом.

Требования:
- 150-250 слов
- Конкретная полезная информация
- Вдохновляющий тон
- Призыв к действию
- 5-7 хэштегов
- Язык: русский"""

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
