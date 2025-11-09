import logging
import threading
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from ..models import Tweet, ScrapingSession
from ..serializers import (
    ScrapeTweetsRequestSerializer,
    ScrapeTweetsResponseSerializer,
    ErrorResponseSerializer,
)
from ..services import (
    create_twitter_scraper,
    DataProcessor,
)

logger = logging.getLogger(__name__)


class ScrapeTweetsAPIView(APIView):
    """API endpoint to scrape tweets"""

    def _scrape_and_process(self, session_id: int, use_twikit: bool = None):
        """Background task to scrape and process tweets"""
        session = None
        try:
            session = ScrapingSession.objects.get(id=session_id)
            scraper = create_twitter_scraper(use_twikit=use_twikit, max_workers=3)
            processor = DataProcessor(output_dir="data")

            raw_tweets = scraper.scrape_all_hashtags()
            if len(raw_tweets) < 2000:
                logger.warning(f"Only collected {len(raw_tweets)} tweets")

            processed_tweets = processor.process_tweets(raw_tweets)
            processed_tweets = processor.deduplicate(processed_tweets)

            logger.info("Saving tweets to database...")
            saved_count = 0
            for tweet_data in processed_tweets:
                try:
                    Tweet.objects.get_or_create(
                        content_hash=tweet_data['content_hash'],
                        defaults={
                            'username': tweet_data['username'],
                            'timestamp': tweet_data['timestamp'],
                            'content': tweet_data['content'],
                            'likes': tweet_data['likes'],
                            'retweets': tweet_data['retweets'],
                            'replies': tweet_data['replies'],
                            'mentions': tweet_data['mentions'],
                            'hashtags': tweet_data['hashtags'],
                            'tweet_id': tweet_data.get('tweet_id'),
                            'url': tweet_data.get('url'),
                        }
                    )
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"Error saving tweet: {e}")
                    continue

            # Save to Parquet
            parquet_path = processor.save_to_parquet(processed_tweets)

            # Update session
            session.tweets_collected = saved_count
            session.status = 'completed'
            session.completed_at = timezone.now()
            session.save()

            logger.info(f"Scraping completed: {saved_count} tweets saved")

        except Exception as e:
            logger.error(f"Error in scraping process: {e}")
            if session:
                session.status = 'failed'
                session.errors = session.errors + [str(e)]
                session.completed_at = timezone.now()
                session.save()


    @swagger_auto_schema(
        operation_description="Start scraping tweets from Twitter/X. The scraping process runs in the background. "
                              "Use the session_id to track progress. You can optionally specify which scraper to use.",
        request_body=ScrapeTweetsRequestSerializer,
        responses={
            202: ScrapeTweetsResponseSerializer,
            500: ErrorResponseSerializer,
        },
        tags=['Scraping']
    )
    def post(self, request):
        """Start scraping process"""
        try:
            # Create scraping session
            session = ScrapingSession.objects.create(status='running')
            
            # Get scraper preference from request
            use_twikit = request.data.get('use_twikit', None) if hasattr(request, 'data') else None
            
            # Start scraping in background thread
            thread = threading.Thread(
                target=self._scrape_and_process,
                args=(session.id, use_twikit),
                daemon=True
            )
            thread.start()
            
            scraper_type = "Twikit" if use_twikit else ("API" if use_twikit is False else "Auto-detect")
            return Response({
                'status': 'started',
                'session_id': session.id,
                'message': 'Scraping started in background',
                'scraper': scraper_type
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Error starting scrape: {e}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
