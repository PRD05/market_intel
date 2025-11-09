"""
Django management command to scrape tweets from command line
"""
from django.core.management.base import BaseCommand
from scraper.services import TwitterScraper, DataProcessor
from scraper.models import Tweet, ScrapingSession
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Scrape tweets from Twitter/X API for Indian stock market discussions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workers',
            type=int,
            default=3,
            help='Number of concurrent API requests (default: 3)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting tweet scraping...'))
        
        # Create scraping session
        session = ScrapingSession.objects.create(status='running')
        
        try:
            # Initialize components
            scraper = TwitterScraper(
                max_workers=options['workers']
            )
            processor = DataProcessor(output_dir="data")
            
            # Scrape tweets
            self.stdout.write('Scraping tweets from Twitter/X...')
            raw_tweets = scraper.scrape_all_hashtags()
            
            if len(raw_tweets) < 2000:
                self.stdout.write(
                    self.style.WARNING(
                        f'Only collected {len(raw_tweets)} tweets, less than minimum 2000'
                    )
                )
            
            # Process tweets
            self.stdout.write('Processing and cleaning tweets...')
            processed_tweets = processor.process_tweets(raw_tweets)
            processed_tweets = processor.deduplicate(processed_tweets)
            
            # Save to database
            self.stdout.write('Saving tweets to database...')
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
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully scraped and saved {saved_count} tweets!'
                )
            )
            self.stdout.write(f'Parquet file saved to: {parquet_path}')
            
        except Exception as e:
            logger.error(f"Error in scraping: {e}")
            session.status = 'failed'
            session.errors = session.errors + [str(e)]
            session.completed_at = timezone.now()
            session.save()
            self.stdout.write(
                self.style.ERROR(f'Error during scraping: {e}')
            )

