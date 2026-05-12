"""Generic parser for news websites - uses heuristics to find articles"""
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import re
import logging
logger = logging.getLogger(__name__)

from agents.grants_scraper.base import BaseScraper
# relevance_checker removed


class GenericParser(BaseScraper):
    """
    Generic parser that attempts to parse any news/blog website
    Uses common HTML patterns and heuristics
    """

    def __init__(self, source_url: str, source_name: str):
        super().__init__(
            source_url=source_url,
            source_name=source_name
        )

    async def fetch_articles(self) -> List[Dict]:
        """Fetch list of recent articles using generic selectors"""
        articles = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.source_url, timeout=30) as response:
                    if response.status != 200:
                        return articles

                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')

                    # Try multiple common selectors for articles
                    article_selectors = [
                        'article',
                        '.post',
                        '.article',
                        '.news-item',
                        '.entry',
                        '.blog-post',
                        '[class*="article"]',
                        '[class*="post"]',
                        '[class*="entry"]'
                    ]

                    article_items = []
                    for selector in article_selectors:
                        items = soup.select(selector)
                        if items:
                            article_items = items
                            break

                    # Fallback: find all links with titles
                    if not article_items:
                        article_items = soup.find_all('a', href=True)

                    for item in article_items[:20]:  # Limit to 20 articles
                        try:
                            # Try to extract title
                            title = self._extract_title(item)
                            if not title or len(title) < 10:
                                continue

                            # Check relevance by title
                            relevance_result = relevance_checker.check_relevance(title)
                            if not relevance_result['is_relevant']:
                                logger.debug(
                                    f"Skipping irrelevant article: {title[:50]}... "
                                    f"({relevance_result['reason']})"
                                )
                                continue

                            # Try to extract URL
                            url = self._extract_url(item)
                            if not url:
                                continue

                            # Try to extract date
                            date = self._extract_date(item)

                            article = {
                                'title': title,
                                'url': url,
                                'published_at': date
                            }

                            # Avoid duplicates
                            if not any(a['url'] == url for a in articles):
                                articles.append(article)
                                logger.info(
                                    f"✅ Relevant article found: {title[:60]}... "
                                    f"(score: {relevance_result['score']})"
                                )

                        except Exception as e:
                            continue

        except Exception as e:
            print(f"Error fetching articles from {self.source_name}: {e}")

        return articles

    async def parse_article(self, url: str) -> Optional[Dict]:
        """Parse full article content using generic selectors"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status != 200:
                        return None

                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')

                    # Try to extract title
                    title = self._extract_title(soup)

                    # Try to extract content
                    content = self._extract_content(soup)

                    # Try to extract date
                    date = self._extract_date(soup)

                    if not title or not content:
                        return None

                    # Check relevance with full content
                    relevance_result = relevance_checker.check_relevance(title, content)
                    if not relevance_result['is_relevant']:
                        logger.info(
                            f"❌ Article not relevant: {title[:60]}... "
                            f"({relevance_result['reason']})"
                        )
                        return None

                    logger.info(
                        f"✅ Relevant article parsed: {title[:60]}... "
                        f"(score: {relevance_result['score']}, "
                        f"keywords: {', '.join(relevance_result['relevant_matches'][:3])})"
                    )

                    return {
                        'title': title,
                        'content': content,
                        'published_at': date,
                        'url': url
                    }

        except Exception as e:
            print(f"Error parsing article {url}: {e}")
            return None

    def _extract_title(self, element) -> Optional[str]:
        """Extract title using heuristics"""
        # Try multiple title selectors
        title_selectors = [
            'h1',
            'h2',
            '.title',
            '.post-title',
            '.article-title',
            '.entry-title',
            '[class*="title"]'
        ]

        for selector in title_selectors:
            title_elem = element.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                if len(title) > 10:
                    return title

        # Try meta og:title
        if hasattr(element, 'find'):
            meta = element.find('meta', property='og:title')
            if meta and meta.get('content'):
                return meta['content']

        # Try getting text from first h1/h2
        for tag in ['h1', 'h2']:
            elem = element.find(tag)
            if elem:
                text = elem.get_text(strip=True)
                if len(text) > 10:
                    return text

        return None

    def _extract_url(self, element) -> Optional[str]:
        """Extract URL from element"""
        # Try to find link
        if element.name == 'a':
            url = element.get('href')
        else:
            link = element.find('a', href=True)
            url = link['href'] if link else None

        if url:
            return self._make_absolute_url(url)

        return None

    def _extract_date(self, element) -> Optional[datetime]:
        """Extract date using heuristics"""
        # Try multiple date selectors
        date_selectors = [
            'time',
            '.date',
            '.published',
            '.post-date',
            '.entry-date',
            '[class*="date"]',
            '[datetime]'
        ]

        for selector in date_selectors:
            date_elem = element.select_one(selector)
            if date_elem:
                # Try datetime attribute
                datetime_attr = date_elem.get('datetime')
                if datetime_attr:
                    parsed = self._parse_date(datetime_attr)
                    if parsed:
                        return parsed

                # Try text content
                text = date_elem.get_text(strip=True)
                parsed = self._parse_date(text)
                if parsed:
                    return parsed

        # Try meta tags
        if hasattr(element, 'find'):
            meta = element.find('meta', property='article:published_time')
            if meta and meta.get('content'):
                return self._parse_date(meta['content'])

        return None

    def _extract_content(self, soup) -> Optional[str]:
        """Extract main content using heuristics"""
        # Try multiple content selectors
        content_selectors = [
            'article',
            '.content',
            '.post-content',
            '.article-content',
            '.entry-content',
            '.post-body',
            '[class*="content"]',
            'main'
        ]

        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # Remove unwanted elements
                for unwanted in content_elem(['script', 'style', 'nav', 'aside', 'footer', 'header']):
                    unwanted.decompose()

                text = content_elem.get_text(separator='\n', strip=True)
                if len(text) > 100:  # At least 100 chars
                    return text

        return None

    def _make_absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute"""
        if url.startswith('http'):
            return url

        from urllib.parse import urljoin
        return urljoin(self.source_url, url)
