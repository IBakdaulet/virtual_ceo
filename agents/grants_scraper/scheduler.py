"""Scheduler for automatic scraping tasks"""
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
import asyncio
from zoneinfo import ZoneInfo

from src.config import settings
from src.database.connection import get_session
from src.database.repositories.article_repo import ArticleRepository
from src.database.models import Source
from src.scraper.base import BaseScraper
from src.utils.task_monitor import task_monitor


class ScraperScheduler:
    """Manages scheduled scraping tasks"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.parsers = {}  # Will hold parser instances

    def start(self):
        """Start the scheduler"""
        # NEW: Schedule article processing at specific hours
        if hasattr(settings, 'ENABLE_ARTICLE_MODE') and settings.ENABLE_ARTICLE_MODE:
            scraping_hours = settings.SCRAPING_HOURS if hasattr(settings, 'SCRAPING_HOURS') else '9,14,18'
            tz = ZoneInfo(settings.TIMEZONE)
            self.scheduler.add_job(
                self.run_article_processing,
                trigger=CronTrigger(
                    hour=scraping_hours,
                    minute=0,
                    timezone=tz
                ),
                id='article_processing',
                replace_existing=True,
                name=f'Article Processing ({scraping_hours})'
            )
            logger.info(
                f"Article processing mode enabled. Running at hours: {scraping_hours} ({settings.TIMEZONE})"
            )

        # OLD: Keep daily scraping for digest mode (backward compatibility)
        if hasattr(settings, 'ENABLE_DIGEST_MODE') and settings.ENABLE_DIGEST_MODE:
            tz_digest = ZoneInfo(settings.TIMEZONE)
            self.scheduler.add_job(
                self.run_daily_scraping,
                trigger=CronTrigger(hour=settings.SCRAPING_SCHEDULE_HOUR, minute=0, timezone=tz_digest),
                id='daily_scraping',
                replace_existing=True,
                name='Daily News Scraping'
            )
            logger.info(
                f"Digest mode enabled. Daily scraping at {settings.SCRAPING_SCHEDULE_HOUR}:00 ({settings.TIMEZONE})"
            )

        self.scheduler.start()
        logger.info("Scraper scheduler started")

    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Scraper scheduler stopped")

    async def run_daily_scraping(self):
        """Main scraping task - runs daily"""
        logger.info("Starting daily scraping task")
        task_monitor.register_task("daily_scraping")

        max_retries = 3
        retry_delay = 60  # seconds

        for attempt in range(max_retries):
            try:
                async with get_session() as session:
                    # Get all active sources
                    from sqlalchemy import select
                    result = await session.execute(
                        select(Source).where(Source.is_active == True)
                    )
                    sources = result.scalars().all()

                    if not sources:
                        logger.warning("No active sources found")
                        task_monitor.record_run("daily_scraping", success=True)
                        return

                    article_repo = ArticleRepository(session)
                    total_new_articles = 0
                    failed_sources = []

                    for source in sources:
                        try:
                            new_count = await self._scrape_source_with_retry(
                                source, article_repo
                            )
                            total_new_articles += new_count
                            logger.info(
                                f"Scraped {new_count} new articles from {source.name}"
                            )

                            # Update last_checked_at
                            from datetime import datetime
                            source.last_checked_at = datetime.now()

                        except Exception as e:
                            logger.error(f"Error scraping {source.name}: {e}")
                            failed_sources.append(source.name)
                            continue

                    await session.commit()

                    # Log summary
                    summary = f"Daily scraping completed. Total new articles: {total_new_articles}"
                    if failed_sources:
                        summary += f". Failed sources: {', '.join(failed_sources)}"
                    logger.info(summary)

                    # Record successful run
                    task_monitor.record_run("daily_scraping", success=True)

                    # If we have enough articles, trigger digest creation
                    if total_new_articles >= settings.MIN_ARTICLES_FOR_DIGEST:
                        await self._trigger_digest_creation()

                    return  # Success - exit retry loop

            except Exception as e:
                error_msg = f"Error in daily scraping task (attempt {attempt + 1}/{max_retries}): {e}"
                logger.error(error_msg)

                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    # Final attempt failed
                    task_monitor.record_run("daily_scraping", success=False, error=str(e))
                    logger.error("Daily scraping failed after all retry attempts")

    async def run_article_processing(self):
        """
        NEW: Process articles every 4 hours - individual article mode

        This method:
        1. Scrapes all active sources
        2. For each new article:
           - Creates a brief summary (max 5 sentences)
           - Creates a Post with article_id
           - Sends to moderator immediately
        """
        logger.info("Starting article processing task (every 4 hours)")
        task_monitor.register_task("article_processing")

        max_retries = 3
        retry_delay = 60  # seconds

        for attempt in range(max_retries):
            try:
                async with get_session() as session:
                    # Get all active sources
                    from sqlalchemy import select
                    result = await session.execute(
                        select(Source).where(Source.is_active == True)
                    )
                    sources = result.scalars().all()

                    if not sources:
                        logger.warning("No active sources found")
                        task_monitor.record_run("article_processing", success=True)
                        return

                    article_repo = ArticleRepository(session)
                    total_new_articles = 0
                    total_processed_posts = 0
                    failed_sources = []

                    for source in sources:
                        try:
                            # Scrape source
                            new_count = await self._scrape_source_with_retry(
                                source, article_repo
                            )
                            total_new_articles += new_count

                            if new_count > 0:
                                logger.info(
                                    f"Scraped {new_count} new articles from {source.name}"
                                )

                            # Update last_checked_at
                            from datetime import datetime
                            source.last_checked_at = datetime.now()

                        except Exception as e:
                            logger.error(f"Error scraping {source.name}: {e}")
                            failed_sources.append(source.name)
                            continue

                    await session.commit()

                    # Process unprocessed articles (regardless of new articles found)
                    from src.services.article_post_service import ArticlePostService
                    from telegram import Bot
                    from datetime import datetime, timedelta

                    # Get bot instance
                    try:
                        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                    except Exception as e:
                        logger.error(f"Error creating bot instance: {e}")
                        bot = None

                    article_post_service = ArticlePostService(session, bot)

                    # Get unprocessed articles published/scraped within last 14 days
                    from src.database.models import Article
                    max_age_days = 14
                    cutoff_date = datetime.now() - timedelta(days=max_age_days)

                    result = await session.execute(
                        select(Article)
                        .where(Article.is_processed == False)
                        .where(
                            # Use published_at if available, otherwise use scraped_at
                            (
                                (Article.published_at >= cutoff_date) |
                                ((Article.published_at.is_(None)) & (Article.scraped_at >= cutoff_date))
                            )
                        )
                    )
                    unprocessed_articles = result.scalars().all()

                    if unprocessed_articles:
                        logger.info(f"Processing {len(unprocessed_articles)} unprocessed articles...")

                        for article in unprocessed_articles:
                            try:
                                # Check if already processed
                                if await article_post_service.has_article_been_processed(article.id):
                                    logger.debug(f"Article {article.id} already processed, skipping")
                                    continue

                                # Process article
                                post = await article_post_service.process_article(article)

                                if post:
                                    total_processed_posts += 1
                                    logger.info(
                                        f"✅ Article {article.id} processed as post {post.id}"
                                    )

                                    # Mark article as processed
                                    article.is_processed = True

                            except Exception as e:
                                logger.error(
                                    f"Error processing article {article.id}: {e}"
                                )
                                continue

                        await session.commit()
                    else:
                        logger.info("No unprocessed articles found")

                    # Log summary
                    summary = (
                        f"Article processing completed. "
                        f"New articles: {total_new_articles}, "
                        f"Posts created: {total_processed_posts}"
                    )
                    if failed_sources:
                        summary += f". Failed sources: {', '.join(failed_sources)}"
                    logger.info(summary)

                    # Record successful run
                    task_monitor.record_run("article_processing", success=True)

                    return  # Success - exit retry loop

            except Exception as e:
                error_msg = f"Error in article processing task (attempt {attempt + 1}/{max_retries}): {e}"
                logger.error(error_msg)

                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    # Final attempt failed
                    task_monitor.record_run("article_processing", success=False, error=str(e))
                    logger.error("Article processing failed after all retry attempts")

    async def _scrape_source_with_retry(
        self, source: Source, article_repo: ArticleRepository, max_retries: int = 2
    ) -> int:
        """
        Scrape a source with retry mechanism

        Args:
            source: Source model instance
            article_repo: Article repository
            max_retries: Maximum number of retry attempts

        Returns:
            Number of new articles saved
        """
        for attempt in range(max_retries):
            try:
                return await self._scrape_source(source, article_repo)
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries - 1} for {source.name}: {e}"
                    )
                    await asyncio.sleep(30)  # Wait 30 seconds before retry
                else:
                    raise  # Re-raise on final attempt

        return 0  # Should never reach here

    async def _scrape_source(
        self, source: Source, article_repo: ArticleRepository
    ) -> int:
        """
        Scrape a single source

        Args:
            source: Source model instance
            article_repo: Article repository

        Returns:
            Number of new articles saved
        """
        # Dynamically import parser class
        parser = self._get_parser(source.parser_class, source)
        if not parser:
            logger.error(f"Parser {source.parser_class} not found")
            return 0

        # Fetch articles
        articles = await parser.fetch_articles()
        logger.info(f"Fetched {len(articles)} articles from {source.name}")

        new_articles = 0
        stats = {
            'fetched': len(articles),
            'already_exists': 0,
            'parse_failed': 0,
            'not_relevant': 0,
            'saved': 0,
            'errors': 0
        }

        for article_data in articles:
            try:
                # Check if article already exists
                existing = await article_repo.get_by_url(article_data['url'])
                if existing:
                    stats['already_exists'] += 1
                    continue

                # Parse full article content
                full_article = await parser.parse_article(article_data['url'])
                if not full_article:
                    stats['parse_failed'] += 1
                    continue

                # Check relevance
                if not await parser.is_relevant(full_article):
                    stats['not_relevant'] += 1
                    logger.debug(f"Article not relevant: {full_article['title'][:50]}...")
                    continue

                # Save to database
                await article_repo.create(
                    source_id=source.id,
                    title=full_article['title'],
                    url=full_article['url'],
                    content=full_article['content'],
                    published_at=full_article.get('published_at'),
                    is_processed=False
                )

                stats['saved'] += 1
                new_articles += 1

            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error processing article {article_data.get('url')}: {e}")
                continue

        # Log statistics
        logger.info(
            f"Scraping stats for {source.name}: "
            f"Fetched={stats['fetched']}, "
            f"AlreadyExists={stats['already_exists']}, "
            f"ParseFailed={stats['parse_failed']}, "
            f"NotRelevant={stats['not_relevant']}, "
            f"Saved={stats['saved']}, "
            f"Errors={stats['errors']}"
        )

        return new_articles

    def _get_parser(self, parser_class_name: str, source: Source) -> Optional[BaseScraper]:
        """
        Get parser instance by class name

        Args:
            parser_class_name: Name of the parser class
            source: Source model instance with url and name

        Returns:
            Parser instance or None
        """
        try:
            # Import parsers module
            from src.scraper import parsers
            import importlib
            import inspect

            # Try to get parser class
            module_name = parser_class_name.lower().replace('parser', '_parser')
            module = importlib.import_module(f'src.scraper.parsers.{module_name}')
            parser_class = getattr(module, parser_class_name)

            # Check if parser requires source_url and source_name (like GenericParser)
            sig = inspect.signature(parser_class.__init__)
            params = list(sig.parameters.keys())

            # If parser requires source_url and source_name, pass them
            if 'source_url' in params and 'source_name' in params:
                return parser_class(source_url=source.url, source_name=source.name)
            else:
                # For other parsers (BolashakParser, etc.) - no params needed
                return parser_class()

        except Exception as e:
            logger.error(f"Error loading parser {parser_class_name}: {e}")
            return None

    async def _trigger_digest_creation(self):
        """Trigger digest creation service"""
        try:
            from src.services.digest_service import DigestService

            async with get_session() as session:
                # This will be implemented in services
                logger.info("Triggering digest creation")
                # digest_service = DigestService(session)
                # await digest_service.create_digest_if_ready()

        except Exception as e:
            logger.error(f"Error triggering digest creation: {e}")
