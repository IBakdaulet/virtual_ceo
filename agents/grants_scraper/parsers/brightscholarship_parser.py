"""Bright Scholarship parser for scholarships, internships and fellowships"""
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import json

from agents.grants_scraper.base import BaseScraper


class BrightScholarshipParser(BaseScraper):
    """Parser for Bright Scholarship website"""

    def __init__(self):
        super().__init__(
            source_url="https://brightscholarship.com/",
            source_name="Bright Scholarship"
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

                    # Find all article modules
                    article_modules = soup.select('.td_module_wrap')

                    seen_urls = set()

                    for module in article_modules[:20]:  # Limit to 20
                        try:
                            # Find title link
                            title_link = module.select_one('.entry-title a')
                            if not title_link:
                                continue

                            href = title_link.get('href', '')
                            if not href or href in seen_urls:
                                continue

                            # Get title
                            title = title_link.get_text(strip=True)
                            if not title or len(title) < 10:
                                continue

                            seen_urls.add(href)

                            article = {
                                'title': title,
                                'url': href,
                                'published_at': None  # Will parse from article page
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

                    # Try to extract structured data (Schema.org)
                    title = None
                    published_at = None
                    image_url = None

                    # Look for JSON-LD structured data
                    json_ld_scripts = soup.find_all('script', type='application/ld+json')
                    for script in json_ld_scripts:
                        try:
                            data = json.loads(script.string)
                            if isinstance(data, dict):
                                if data.get('@type') == 'BlogPosting' or data.get('@type') == 'Article':
                                    title = data.get('headline', '')
                                    date_str = data.get('datePublished', '')
                                    if date_str:
                                        try:
                                            published_at = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                        except:
                                            pass
                                    image_data = data.get('image', {})
                                    if isinstance(image_data, dict):
                                        image_url = image_data.get('url', '')
                                    elif isinstance(image_data, str):
                                        image_url = image_data
                        except:
                            continue

                    # Fallback: find title from h1 if not in structured data
                    if not title:
                        title_elem = soup.find('h1')
                        if title_elem:
                            title = title_elem.get_text(strip=True)

                    logger.debug(f"Title found: {title is not None}")

                    if not title:
                        logger.warning(f"No title found for {url}")
                        return None

                    # Find article content
                    # Try multiple selectors for content
                    content_container = (
                        soup.select_one('.entry-content') or
                        soup.select_one('.td-post-content') or
                        soup.select_one('article .post-content') or
                        soup.select_one('.post-content')
                    )

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

                    # Try to find image if not in structured data
                    if not image_url:
                        img_elem = content_container.find('img')
                        if img_elem:
                            img_src = img_elem.get('src') or img_elem.get('data-lazy-src', '')
                            if img_src:
                                # Convert relative URL to absolute
                                if img_src.startswith('//'):
                                    image_url = 'https:' + img_src
                                elif img_src.startswith('/'):
                                    image_url = 'https://brightscholarship.com' + img_src
                                elif img_src.startswith('http'):
                                    image_url = img_src
                                logger.debug(f"Found image: {image_url}")

                    logger.info(f"Successfully parsed article: {title[:50]}... ({len(content_text)} chars)")

                    return {
                        'title': title,
                        'content': content_text,
                        'image_url': image_url,
                        'published_at': published_at,
                        'url': url
                    }

        except Exception as e:
            logger.error(f"Error parsing article {url}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
