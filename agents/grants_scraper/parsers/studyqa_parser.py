"""StudyQA Kazakhstan parser"""
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

from agents.grants_scraper.base import BaseScraper


class StudyQAParser(BaseScraper):
    """Parser for StudyQA education portal"""

    def __init__(self):
        super().__init__(
            source_url="https://studyqa.com/blog",
            source_name="StudyQA Education Blog"
        )

    async def fetch_articles(self) -> List[Dict]:
        """Fetch list of recent articles from StudyQA blog"""
        articles = []

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
                async with session.get(self.source_url, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        return articles

                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')

                    # Try different selectors for blog articles
                    article_items = soup.select('.blog-post, .post, article, .article-item')

                    for item in article_items[:20]:
                        try:
                            # Try different selectors for title and link
                            title_elem = (
                                item.select_one('h2 a') or
                                item.select_one('h3 a') or
                                item.select_one('.post-title a') or
                                item.select_one('a')
                            )

                            link_elem = title_elem or item.select_one('a')

                            date_elem = (
                                item.select_one('.post-date') or
                                item.select_one('.date') or
                                item.select_one('time')
                            )

                            if not title_elem or not link_elem:
                                continue

                            title = title_elem.text.strip()
                            url = self._make_absolute_url(link_elem.get('href', ''))

                            if not url or url == self.source_url:
                                continue

                            # Filter for education abroad related content
                            if not self._is_education_related(title):
                                continue

                            article = {
                                'title': title,
                                'url': url,
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
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
                async with session.get(url, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        return None

                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')

                    # Try to find title
                    title_elem = (
                        soup.select_one('h1') or
                        soup.select_one('.post-title') or
                        soup.select_one('article h1')
                    )

                    # Try to find content
                    content_elem = (
                        soup.select_one('.post-content') or
                        soup.select_one('.article-content') or
                        soup.select_one('article .content') or
                        soup.select_one('.entry-content')
                    )

                    date_elem = (
                        soup.select_one('.post-date') or
                        soup.select_one('time') or
                        soup.select_one('.date')
                    )

                    if not title_elem or not content_elem:
                        return None

                    # Clean content
                    for tag in content_elem(['script', 'style', 'nav', 'aside', 'footer']):
                        tag.decompose()

                    content_text = content_elem.get_text(separator='\n', strip=True)

                    if len(content_text) < 100:
                        return None

                    return {
                        'title': title_elem.text.strip(),
                        'content': content_text,
                        'published_at': self._parse_date(date_elem.text) if date_elem else None,
                        'url': url
                    }

        except Exception as e:
            print(f"Error parsing article {url}: {e}")
            return None

    def _is_education_related(self, text: str) -> bool:
        """Check if content is related to education abroad"""
        keywords = [
            'university', 'universities', 'scholarship', 'study abroad',
            'education', 'student', 'admission', 'degree', 'bachelor',
            'master', 'phd', 'graduate', 'undergraduate', 'college',
            'kazakhstan', 'grants'
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)

    def _make_absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute"""
        if not url:
            return ""

        if url.startswith('http'):
            return url

        from urllib.parse import urljoin
        return urljoin('https://studyqa.com', url)
