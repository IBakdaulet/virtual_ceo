"""Opportunities Corners parser for internships"""
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime

from agents.grants_scraper.base import BaseScraper


class OpportunitiesCornersParser(BaseScraper):
    """Parser for Opportunities Corners website"""

    def __init__(self):
        super().__init__(
            source_url="https://opportunitiescorners.com/category/internships/",
            source_name="Opportunities Corners"
        )

    async def fetch_articles(self) -> List[Dict]:
        """Fetch list of recent internship articles"""
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

                    # Find all article blocks
                    article_blocks = soup.select('.td_module_wrap')

                    seen_urls = set()

                    for block in article_blocks[:20]:  # Limit to 20
                        try:
                            # Get title and link
                            title_link = block.select_one('.entry-title a')
                            if not title_link:
                                continue

                            href = title_link.get('href', '')
                            title = title_link.get_text(strip=True)

                            if not href or href in seen_urls:
                                continue

                            if not title or len(title) < 10:
                                continue

                            seen_urls.add(href)

                            # Try to get date
                            date_elem = block.select_one('.td-post-date time')
                            published_at = None
                            if date_elem:
                                try:
                                    date_str = date_elem.get('datetime')
                                    if date_str:
                                        published_at = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                except:
                                    pass

                            article = {
                                'title': title,
                                'url': href,
                                'published_at': published_at
                            }

                            articles.append(article)

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

                    # Find title
                    title_elem = soup.select_one('.entry-title')
                    if not title_elem:
                        title_elem = soup.find('h1')

                    logger.debug(f"Title element found: {title_elem is not None}")

                    if not title_elem:
                        logger.warning(f"No title element found for {url}")
                        return None

                    # Find article content
                    content_container = soup.select_one('.td-post-content')

                    if not content_container:
                        logger.warning(f"No content container found for {url}")
                        return None

                    # Extract all text elements (paragraphs, headings, lists)
                    content_elements = content_container.find_all(['p', 'h2', 'h3', 'h4', 'ul', 'ol'])
                    logger.debug(f"Found {len(content_elements)} content elements")

                    # Extract text from elements
                    content_parts = []
                    for elem in content_elements:
                        text = elem.get_text(strip=True)
                        # Skip very short elements
                        if len(text) > 20:
                            content_parts.append(text)

                    logger.debug(f"Found {len(content_parts)} meaningful content parts")

                    if not content_parts:
                        logger.warning(f"No meaningful content found for {url}")
                        return None

                    # Combine all content
                    content_text = '\n\n'.join(content_parts)
                    logger.debug(f"Parsed content length: {len(content_text)} chars")

                    # Basic content length check
                    if len(content_text) < 100:
                        logger.warning(f"Content too short for {url}: {len(content_text)} chars (min 100)")
                        return None

                    # Extract first image from article
                    image_url = None
                    img_elem = content_container.find('img')
                    if img_elem:
                        img_src = img_elem.get('src', '')
                        if img_src:
                            # Convert relative URL to absolute
                            if img_src.startswith('//'):
                                image_url = 'https:' + img_src
                            elif img_src.startswith('/'):
                                image_url = 'https://opportunitiescorners.com' + img_src
                            elif img_src.startswith('http'):
                                image_url = img_src
                            logger.debug(f"Found image: {image_url}")

                    logger.info(f"Successfully parsed article: {title_elem.text.strip()[:50]}... ({len(content_text)} chars)")

                    return {
                        'title': title_elem.text.strip(),
                        'content': content_text,
                        'image_url': image_url,
                        'published_at': None,
                        'url': url
                    }

        except Exception as e:
            logger.error(f"Error parsing article {url}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
