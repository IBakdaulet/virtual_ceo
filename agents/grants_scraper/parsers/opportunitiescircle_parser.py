"""Opportunities Circle parser for scholarships and internships"""
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime

from agents.grants_scraper.base import BaseScraper


class OpportunitiesCircleParser(BaseScraper):
    """Parser for Opportunities Circle website"""

    def __init__(self):
        super().__init__(
            source_url="https://www.opportunitiescircle.com/scholarships/",
            source_name="Opportunities Circle"
        )

    async def fetch_articles(self) -> List[Dict]:
        """Fetch list of recent scholarship/internship articles"""
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

                    # Find all article links with Elementor structure
                    # Look for links within heading titles
                    article_links = soup.select('.elementor-heading-title a')

                    seen_urls = set()

                    for link in article_links[:20]:  # Limit to 20
                        try:
                            href = link.get('href', '')
                            if not href or href in seen_urls:
                                continue

                            # Get title from link text
                            title = link.get_text(strip=True)
                            if not title or len(title) < 10:
                                continue

                            seen_urls.add(href)

                            article = {
                                'title': title,
                                'url': href,
                                'published_at': None  # Will try to parse from article page
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
                    title_elem = soup.select_one('.elementor-widget-theme-post-title .elementor-heading-title')
                    if not title_elem:
                        # Fallback to h1
                        title_elem = soup.find('h1')

                    logger.debug(f"Title element found: {title_elem is not None}")

                    if not title_elem:
                        logger.warning(f"No title element found for {url}")
                        return None

                    # Find article content
                    content_container = soup.select_one('.elementor-widget-theme-post-content')

                    if not content_container:
                        logger.warning(f"No content container found for {url}")
                        return None

                    # Extract all paragraphs from content container
                    paragraphs = content_container.find_all('p')
                    logger.debug(f"Found {len(paragraphs)} paragraphs in container")

                    # Filter meaningful paragraphs
                    content_paragraphs = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        # Skip very short paragraphs
                        if len(text) > 30:
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
                    img_elem = content_container.find('img')
                    if img_elem:
                        img_src = img_elem.get('src', '')
                        if img_src:
                            # Convert relative URL to absolute
                            if img_src.startswith('//'):
                                image_url = 'https:' + img_src
                            elif img_src.startswith('/'):
                                image_url = 'https://www.opportunitiescircle.com' + img_src
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
