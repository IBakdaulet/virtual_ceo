"""Example parser implementation - template for creating new parsers"""
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

from agents.grants_scraper.base import BaseScraper


class ExampleParser(BaseScraper):
    """
    Example parser for educational websites
    Copy this file and modify for each specific website
    """

    def __init__(self):
        super().__init__(
            source_url="https://example.com/news",
            source_name="Example Education Portal"
        )

    async def fetch_articles(self) -> List[Dict]:
        """Fetch list of recent articles"""
        articles = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.source_url, timeout=30) as response:
                    if response.status != 200:
                        return articles

                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')

                    # Modify these selectors based on actual website structure
                    article_items = soup.select('.article-item')  # CSS selector for articles

                    for item in article_items:
                        try:
                            title_elem = item.select_one('.article-title')
                            link_elem = item.select_one('a')
                            date_elem = item.select_one('.article-date')

                            if not title_elem or not link_elem:
                                continue

                            article = {
                                'title': title_elem.text.strip(),
                                'url': self._make_absolute_url(link_elem['href']),
                                'published_at': self._parse_date(date_elem.text) if date_elem else None
                            }

                            articles.append(article)

                        except Exception as e:
                            print(f"Error parsing article item: {e}")
                            continue

        except Exception as e:
            print(f"Error fetching articles from {self.source_name}: {e}")

        return articles

    async def parse_article(self, url: str) -> Optional[Dict]:
        """Parse full article content"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status != 200:
                        return None

                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')

                    # Modify these selectors based on actual website structure
                    title_elem = soup.select_one('h1.article-title')
                    content_elem = soup.select_one('.article-content')
                    date_elem = soup.select_one('.article-date')

                    if not title_elem or not content_elem:
                        return None

                    # Extract text from content, removing scripts and styles
                    for script in content_elem(['script', 'style']):
                        script.decompose()

                    return {
                        'title': title_elem.text.strip(),
                        'content': content_elem.get_text(separator='\n', strip=True),
                        'published_at': self._parse_date(date_elem.text) if date_elem else None,
                        'url': url
                    }

        except Exception as e:
            print(f"Error parsing article {url}: {e}")
            return None

    def _make_absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute"""
        if url.startswith('http'):
            return url

        from urllib.parse import urljoin
        return urljoin(self.source_url, url)
