"""Input validation utilities"""
from urllib.parse import urlparse
from typing import Optional
from loguru import logger


class URLValidator:
    """Validate and sanitize URLs"""

    # Whitelist of allowed domains for parsing
    ALLOWED_DOMAINS = [
        'topuniversities.com',
        'studyqa.com',
        'educationabroad.com',
        'opportunitiescircle.com',
        'opportunitiescorners.com',
        'globalscholarships.com',
        'brightscholarship.com',
        'bolashak.gov.kz',
        'spubl.ru'
    ]

    @staticmethod
    def validate_url(url: str, check_whitelist: bool = True) -> bool:
        """
        Validate URL format and optionally check against whitelist

        Args:
            url: URL to validate
            check_whitelist: If True, only allow whitelisted domains

        Returns:
            bool: True if URL is valid, False otherwise

        Example:
            >>> validator = URLValidator()
            >>> validator.validate_url("https://example.com/article")
            True
            >>> validator.validate_url("javascript:alert(1)")
            False
        """
        if not url or not isinstance(url, str):
            logger.warning(f"Invalid URL type: {type(url)}")
            return False

        try:
            result = urlparse(url)

            # Check scheme
            if result.scheme not in ['http', 'https']:
                logger.warning(f"Invalid URL scheme: {result.scheme}")
                return False

            # Check netloc (domain)
            if not result.netloc:
                logger.warning(f"Missing domain in URL: {url}")
                return False

            # Check whitelist if required
            if check_whitelist:
                domain = result.netloc.lower()
                # Remove www. prefix
                if domain.startswith('www.'):
                    domain = domain[4:]

                if not any(domain.endswith(allowed) for allowed in URLValidator.ALLOWED_DOMAINS):
                    logger.warning(f"Domain not in whitelist: {domain}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating URL {url}: {e}")
            return False

    @staticmethod
    def sanitize_url(url: str) -> Optional[str]:
        """
        Sanitize URL by removing dangerous characters and validating

        Args:
            url: URL to sanitize

        Returns:
            Sanitized URL or None if invalid

        Example:
            >>> validator = URLValidator()
            >>> validator.sanitize_url("https://example.com/<script>")
            "https://example.com/%3Cscript%3E"
        """
        if not url:
            return None

        # Remove leading/trailing whitespace
        url = url.strip()

        # Validate
        if not URLValidator.validate_url(url, check_whitelist=False):
            return None

        # Parse and reconstruct to sanitize
        try:
            parsed = urlparse(url)
            # Reconstruct URL with validated components
            sanitized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                sanitized += f"?{parsed.query}"

            return sanitized

        except Exception as e:
            logger.error(f"Error sanitizing URL {url}: {e}")
            return None


class TextValidator:
    """Validate text input"""

    @staticmethod
    def validate_digest_content(content: str, max_length: int = 10000) -> bool:
        """
        Validate digest content

        Args:
            content: Content to validate
            max_length: Maximum allowed length

        Returns:
            bool: True if valid
        """
        if not content or not isinstance(content, str):
            return False

        if len(content) > max_length:
            logger.warning(f"Content too long: {len(content)} > {max_length}")
            return False

        # Check for suspicious patterns
        suspicious_patterns = [
            '<script',
            'javascript:',
            'onerror=',
            'onclick=',
        ]

        content_lower = content.lower()
        for pattern in suspicious_patterns:
            if pattern in content_lower:
                logger.warning(f"Suspicious pattern detected: {pattern}")
                return False

        return True

    @staticmethod
    def sanitize_text(text: str, max_length: int = 10000) -> str:
        """
        Sanitize text by removing dangerous content

        Args:
            text: Text to sanitize
            max_length: Maximum length

        Returns:
            Sanitized text
        """
        if not text:
            return ""

        # Truncate
        text = text[:max_length]

        # Remove null bytes
        text = text.replace('\x00', '')

        return text.strip()
