"""SPUBL.kz parser for educational and scientific publications"""
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime

from agents.grants_scraper.base import BaseScraper


class SpublParser(BaseScraper):
    """Parser for SPUBL.kz blog"""

    def __init__(self):
        super().__init__(
            source_url="https://spubl.kz/ru/blog/",
            source_name="SPUBL.kz"
        )

    async def fetch_articles(self) -> List[Dict]:
        """Fetch list of recent blog articles"""
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

                    # Find all blog post links
                    # Look for links that contain /ru/blog/ and are post links (not categories)
                    all_links = soup.find_all('a', href=True)

                    seen_urls = set()

                    for link in all_links:
                        try:
                            href = link.get('href', '')

                            # Filter blog post links
                            if '/ru/blog/' not in href:
                                continue

                            # Skip category and pagination links
                            if '?page=' in href or '/category/' in href:
                                continue

                            # Ensure full URL
                            if href.startswith('/'):
                                href = 'https://spubl.kz' + href
                            elif not href.startswith('http'):
                                continue

                            if href in seen_urls or href == self.source_url:
                                continue

                            # Get title - try from h4 tag or link text
                            title = None

                            # Look for h4 in parent or as child
                            h4 = link.find('h4') or link.find_parent('h4')
                            if h4:
                                title = h4.get_text(strip=True)
                            else:
                                title = link.get_text(strip=True)

                            if not title or len(title) < 10:
                                continue

                            # Clean title
                            if 'Читать далее' in title:
                                continue

                            seen_urls.add(href)

                            article = {
                                'title': title,
                                'url': href,
                                'published_at': None
                            }

                            articles.append(article)

                            if len(articles) >= 20:  # Limit to 20
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

                    # Find title
                    title_elem = soup.find('h1') or soup.find('h2')

                    if not title_elem:
                        logger.warning(f"No title found for {url}")
                        return None

                    title = title_elem.get_text(strip=True)

                    logger.debug(f"Title found: {title}")

                    # Find content container
                    # Try multiple selectors
                    content_container = (
                        soup.select_one('.entry-content') or
                        soup.select_one('.post-content') or
                        soup.select_one('article .content') or
                        soup.select_one('.blog-post-content') or
                        soup.find('article')
                    )

                    if not content_container:
                        logger.warning(f"No content container found for {url}")
                        return None

                    # Extract paragraphs
                    paragraphs = content_container.find_all('p')
                    logger.debug(f"Found {len(paragraphs)} paragraphs")

                    # Filter meaningful paragraphs
                    content_paragraphs = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        # Skip very short paragraphs and "Read more" text
                        if len(text) > 30 and 'Читать далее' not in text:
                            content_paragraphs.append(text)

                    logger.debug(f"Found {len(content_paragraphs)} meaningful paragraphs")

                    if not content_paragraphs:
                        logger.warning(f"No meaningful paragraphs found for {url}")
                        return None

                    # Combine content
                    content_text = '\n\n'.join(content_paragraphs)
                    logger.debug(f"Parsed content length: {len(content_text)} chars")

                    if len(content_text) < 100:
                        logger.warning(f"Content too short for {url}")
                        return None

                    # Try to find publication date
                    published_at = None
                    date_elem = soup.select_one('.post-date') or soup.select_one('.entry-date')
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        # Try to parse date (format: DD. MM. YYYY)
                        try:
                            published_at = datetime.strptime(date_text, '%d. %m. %Y')
                        except:
                            pass

                    # Find image
                    image_url = None
                    img_elem = content_container.find('img')
                    if img_elem:
                        img_src = (
                            img_elem.get('src') or
                            img_elem.get('data-src') or
                            img_elem.get('data-pagespeed-lazy-src', '')
                        )
                        if img_src:
                            if img_src.startswith('//'):
                                image_url = 'https:' + img_src
                            elif img_src.startswith('/'):
                                image_url = 'https://spubl.kz' + img_src
                            elif img_src.startswith('http'):
                                image_url = img_src

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
