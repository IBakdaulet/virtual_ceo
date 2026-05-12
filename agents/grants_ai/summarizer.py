"""AI content summarizer using OpenAI API"""
from openai import AsyncOpenAI
from typing import List
from loguru import logger

from src.config import settings
from src.ai.prompts import (
    SYSTEM_PROMPT_DIGEST_CREATOR,
    SYSTEM_PROMPT_SINGLE_ARTICLE,
    get_digest_creation_prompt,
    get_single_article_summary_prompt
)


class ContentSummarizer:
    """Creates digests from articles using OpenAI API"""

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize summarizer

        Args:
            api_key: OpenAI API key (defaults to settings)
            model: Model to use (defaults to settings)
        """
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.client = AsyncOpenAI(api_key=self.api_key)

    async def create_digest(self, articles: List[dict]) -> str:
        """
        Create digest from multiple articles

        Args:
            articles: List of article dictionaries with 'title' and 'content'

        Returns:
            Generated digest text

        Raises:
            Exception: If API call fails
        """
        if not articles:
            raise ValueError("Articles list is empty")

        if len(articles) < settings.MIN_ARTICLES_FOR_DIGEST:
            logger.warning(
                f"Less than {settings.MIN_ARTICLES_FOR_DIGEST} articles provided"
            )

        try:
            prompt = get_digest_creation_prompt(articles)

            logger.info(f"Creating digest from {len(articles)} articles using {self.model}")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_DIGEST_CREATOR},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500,
            )

            digest = response.choices[0].message.content.strip()

            logger.info(f"Digest created successfully. Length: {len(digest)} characters")

            return digest

        except Exception as e:
            logger.error(f"Error creating digest: {e}")
            raise

    async def summarize_single_article(
        self,
        article_title: str,
        article_content: str,
        article_url: str
    ) -> str:
        """
        Create a brief summary (max 5 sentences) from a single article

        Args:
            article_title: Article title
            article_content: Article content
            article_url: Article URL

        Returns:
            Generated summary text (max 5 sentences)

        Raises:
            Exception: If API call fails
        """
        try:
            prompt = get_single_article_summary_prompt(
                article_title,
                article_content,
                article_url
            )

            logger.info(f"Creating summary for article: {article_title[:60]}...")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_SINGLE_ARTICLE},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800,  # Shorter than digest since it's just one article
            )

            summary = response.choices[0].message.content.strip()

            logger.info(f"Summary created successfully. Length: {len(summary)} characters")

            return summary

        except Exception as e:
            logger.error(f"Error creating summary for article: {e}")
            raise

    async def improve_text(self, original_text: str, instructions: str) -> str:
        """
        Improve or edit text based on instructions

        Args:
            original_text: Original text to improve
            instructions: User instructions for improvement

        Returns:
            Improved text

        Raises:
            Exception: If API call fails
        """
        try:
            from src.ai.prompts import get_improve_text_prompt

            prompt = get_improve_text_prompt(original_text, instructions)

            logger.info("Improving text based on user instructions")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_DIGEST_CREATOR},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500,
            )

            improved_text = response.choices[0].message.content.strip()

            logger.info("Text improved successfully")

            return improved_text

        except Exception as e:
            logger.error(f"Error improving text: {e}")
            raise

    async def analyze_relevance(self, title: str, content: str) -> bool:
        """
        Analyze if content is relevant to education abroad

        Args:
            title: Article title
            content: Article content (will be truncated)

        Returns:
            True if relevant, False otherwise
        """
        try:
            from src.ai.prompts import SYSTEM_PROMPT_CONTENT_ANALYZER, get_content_analysis_prompt

            prompt = get_content_analysis_prompt(title, content)

            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Use cheaper model for analysis
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_CONTENT_ANALYZER},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=10,
            )

            answer = response.choices[0].message.content.strip().lower()

            return "да" in answer or "yes" in answer

        except Exception as e:
            logger.error(f"Error analyzing relevance: {e}")
            # Default to True to avoid losing potentially relevant articles
            return True
