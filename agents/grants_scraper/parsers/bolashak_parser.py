"""Bolashak International Scholarship parser - improved universal version"""
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime

from agents.grants_scraper.base import BaseScraper


class BolashakParser(BaseScraper):
    """Parser for Bolashak International Scholarship website"""

    def __init__(self):
        super().__init__(
            source_url="https://bolashak.gov.kz/ru/allnews/",  # Updated URL
            source_name="Bolashak International Scholarship"
        )

    async def fetch_articles(self) -> List[Dict]:
        """Fetch list of recent articles - universal approach"""
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

                    # Universal approach: find all links that look like news articles
                    # Look for links containing /allnews/ or similar patterns
                    all_links = soup.find_all('a', href=True)

                    seen_urls = set()

                    for link in all_links:
                        try:
                            href = link.get('href', '')

                            # Skip if not a news article
                            if not href or href == '#' or href == '/':
                                continue

                            # Look for links containing news-related keywords
                            if not any(keyword in href.lower() for keyword in ['news', 'novosti', 'allnews']):
                                continue

                            # Get absolute URL
                            url = self._make_absolute_url(href)

                            # Skip duplicates
                            if url in seen_urls or url == self.source_url:
                                continue

                            seen_urls.add(url)

                            # Get title from link text or nearby heading
                            title = link.get_text(strip=True)

                            # If title is too short, try to find nearby heading
                            if len(title) < 10:
                                parent = link.parent
                                if parent:
                                    heading = parent.find(['h1', 'h2', 'h3', 'h4'])
                                    if heading:
                                        title = heading.get_text(strip=True)

                            # Skip if title is still too short or empty
                            if not title or len(title) < 10:
                                continue

                            # Try to find date
                            date_elem = None
                            parent = link.parent
                            if parent:
                                date_elem = parent.find(['time', 'span'], class_=lambda x: x and 'date' in x.lower() if x else False)

                            article = {
                                'title': title,
                                'url': url,
                                'published_at': self._parse_date(date_elem.text) if date_elem else None
                            }

                            articles.append(article)

                            # Limit to 20 articles
                            if len(articles) >= 20:
                                break

                        except Exception as e:
                            continue

        except Exception as e:
            print(f"Error fetching articles from {self.source_name}: {e}")

        return articles

    async def parse_article(self, url: str) -> Optional[Dict]:
        """Parse full article content"""
        import logging
logger = logging.getLogger(__name__)

        logger.debug(f"Starting to parse article: {url}")

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
                async with session.get(url, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch article {url}: HTTP {response.status}")
                        return None

                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')

                    # Bolashak-specific: Find title in h1
                    title_elem = soup.find('h1')
                    logger.debug(f"Title element found: {title_elem is not None}")

                    if not title_elem:
                        logger.warning(f"No title element found for {url}")
                        return None

                    # Bolashak-specific: Content is in div with class 'blogvnut' or 'vnutstran'
                    # This div contains the article paragraphs
                    article_container = soup.find('div', class_='blogvnut') or soup.find('div', class_='vnutstran')

                    if not article_container:
                        logger.warning(f"No article container (blogvnut/vnutstran) found for {url}")
                        return None

                    # Extract all paragraphs from article container
                    paragraphs = article_container.find_all('p')
                    logger.debug(f"Found {len(paragraphs)} paragraphs in container")

                    # Filter out navigation breadcrumbs and get only meaningful paragraphs
                    content_paragraphs = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        # Skip very short paragraphs (likely navigation or headers)
                        if len(text) > 40:
                            content_paragraphs.append(text)

                    logger.debug(f"Found {len(content_paragraphs)} meaningful paragraphs")

                    if not content_paragraphs:
                        logger.warning(f"No meaningful paragraphs found for {url}")
                        return None

                    # Combine all paragraphs into content
                    content_text = '\n\n'.join(content_paragraphs)
                    logger.debug(f"Parsed content length: {len(content_text)} chars")

                    # Basic content length check
                    if len(content_text) < 100:
                        logger.warning(f"Content too short for {url}: {len(content_text)} chars (min 100)")
                        return None

                    # Extract first image from article
                    image_url = None
                    img_elem = article_container.find('img')
                    if img_elem:
                        img_src = img_elem.get('src', '')
                        if img_src:
                            # Convert relative URL to absolute
                            if img_src.startswith('//'):
                                image_url = 'https:' + img_src
                            elif img_src.startswith('/'):
                                image_url = 'https://bolashak.gov.kz' + img_src
                            elif img_src.startswith('http'):
                                image_url = img_src
                            logger.debug(f"Found image: {image_url}")

                    logger.info(f"Successfully parsed article: {title_elem.text.strip()[:50]}... ({len(content_text)} chars)")

                    return {
                        'title': title_elem.text.strip(),
                        'content': content_text,
                        'image_url': image_url,
                        'published_at': None,  # Will be set from list page
                        'url': url
                    }

        except Exception as e:
            logger.error(f"Error parsing article {url}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _make_absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute"""
        if not url:
            return ""

        if url.startswith('http'):
            return url

        from urllib.parse import urljoin
        return urljoin('https://bolashak.gov.kz', url)
