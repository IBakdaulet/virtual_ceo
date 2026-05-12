"""Base scraper class for all parsers"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime
import logging
from agents.grants_utils import URLValidator

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for all website scrapers"""

    def __init__(self, source_url: str, source_name: str):
        # Validate source URL
        if not URLValidator.validate_url(source_url, check_whitelist=False):
            raise ValueError(f"Invalid source URL: {source_url}")

        self.source_url = source_url
        self.source_name = source_name
        self.url_validator = URLValidator()

    @abstractmethod
    async def fetch_articles(self) -> List[Dict]:
        """
        Fetch list of articles from the website

        Returns:
            List of dictionaries with keys: title, url, published_at
        """
        pass

    @abstractmethod
    async def parse_article(self, url: str) -> Optional[Dict]:
        """
        Parse individual article content

        Args:
            url: Article URL

        Returns:
            Dictionary with keys: title, content, published_at
        """
        pass

    def validate_article_url(self, url: str) -> bool:
        """
        Validate article URL before parsing

        Args:
            url: Article URL to validate

        Returns:
            bool: True if URL is valid and safe to parse
        """
        if not self.url_validator.validate_url(url, check_whitelist=True):
            logger.warning(f"Invalid article URL rejected: {url}")
            return False
        return True

    async def is_relevant(self, article: Dict) -> bool:
        """
        Check if article is relevant to education abroad

        Args:
            article: Article dictionary with title and content

        Returns:
            True if relevant, False otherwise
        """
        keywords = [
            'грант', 'стипендия', 'обучение', 'магистратура', 'бакалавриат',
            'университет', 'колледж', 'образование', 'поступление', 'учеба',
            'студент', 'за рубежом', 'зарубеж', 'scholarship', 'grant',
            'study abroad', 'university', 'college'
        ]

        title = article.get('title', '').lower()
        content = article.get('content', '').lower()

        return any(keyword in title or keyword in content for keyword in keywords)

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string to datetime object
        Override this method for specific date formats

        Args:
            date_str: Date string from website

        Returns:
            datetime object or None if parsing fails
        """
        try:
            # Common date formats
            from dateutil.parser import parse
            return parse(date_str)
        except Exception:
            return None
