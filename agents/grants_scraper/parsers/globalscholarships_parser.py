"""Global Scholarships parser for scholarships and grants"""
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import json

from agents.grants_scraper.base import BaseScraper


class GlobalScholarshipsParser(BaseScraper):
    """Parser for Global Scholarships website"""

    def __init__(self):
        super().__init__(
            source_url="https://globalscholarships.com/scholarship-search/nationality-kazakhstan/",
            source_name="Global Scholarships"
        )

    async def fetch_articles(self) -> List[Dict]:
        """Fetch list of recent scholarship articles for Kazakhstan"""
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

                    # Try multiple selectors for scholarship links
                    # Common WordPress/Fusion patterns
                    selectors = [
                        '.fusion-post-grid article a',
                        '.fusion-posts-container article a',
                        'article.post a',
                        '.post-content a',
                        'h2 a',
                        'h3 a',
                    ]

                    seen_urls = set()
                    found_links = []

                    for selector in selectors:
                        links = soup.select(selector)
                        if links:
                            found_links.extend(links)

                    # Filter and process links
                    for link in found_links[:30]:  # Limit to 30
                        try:
                            href = link.get('href', '')

                            # Skip non-scholarship links
                            if not href or href in seen_urls:
                                continue

                            # Only get links from the same domain
                            if not href.startswith('https://globalscholarships.com'):
                                if href.startswith('/'):
                                    href = 'https://globalscholarships.com' + href
                                else:
                                    continue

                            # Skip search, category, tag pages
                            if any(x in href for x in ['/category/', '/tag/', '/search/', '/page/']):
                                continue

                            # Get title
                            title = link.get_text(strip=True)
                            if not title or len(title) < 10:
                                # Try to find title in parent heading
                                parent = link.find_parent(['h1', 'h2', 'h3', 'h4'])
                                if parent:
                                    title = parent.get_text(strip=True)

                            if not title or len(title) < 10:
                                continue

                            seen_urls.add(href)

                            article = {
                                'title': title,
                                'url': href,
                                'published_at': None
                            }

                            articles.append(article)

                        except Exception as e:
                            continue

        except Exception as e:
            print(f"Error fetching articles from {self.source_name}: {e}")

        return articles

    async def parse_article(self, url: str) -> Optional[Dict]:
        """Parse full scholarship article content"""
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

                    # Try to extract structured data
                    title = None
                    published_at = None
                    image_url = None

                    # Look for JSON-LD structured data
                    json_ld_scripts = soup.find_all('script', type='application/ld+json')
                    for script in json_ld_scripts:
                        try:
                            data = json.loads(script.string)
                            if isinstance(data, dict):
                                if data.get('@type') in ['Article', 'BlogPosting', 'ScholarshipPosting']:
                                    title = data.get('headline', '') or data.get('name', '')
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

                    # Fallback: find title
                    if not title:
                        title_elem = soup.select_one('h1.entry-title') or soup.find('h1')
                        if title_elem:
                            title = title_elem.get_text(strip=True)

                    logger.debug(f"Title found: {title is not None}")

                    if not title:
                        logger.warning(f"No title found for {url}")
                        return None

                    # Find content - try multiple patterns
                    content_container = (
                        soup.select_one('.post-content') or
                        soup.select_one('.entry-content') or
                        soup.select_one('article .content') or
                        soup.select_one('.fusion-post-content') or
                        soup.select_one('article')
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
                        if len(text) > 30:
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

                    # Find image if not in structured data
                    if not image_url:
                        img_elem = content_container.find('img')
                        if img_elem:
                            img_src = img_elem.get('src') or img_elem.get('data-src', '')
                            if img_src:
                                if img_src.startswith('//'):
                                    image_url = 'https:' + img_src
                                elif img_src.startswith('/'):
                                    image_url = 'https://globalscholarships.com' + img_src
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
