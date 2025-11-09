"""
Django management command to analyze tweets and generate signals
"""
from django.core.management.base import BaseCommand
from scraper.services import TweetAnalyzer
from scraper.models import Tweet, TweetSignal
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Analyze tweets and generate trading signals'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting tweet analysis...'))
        
        try:
            # Get tweets from last 24 hours
            cutoff = timezone.now() - timedelta(hours=24)
            tweets = Tweet.objects.filter(timestamp__gte=cutoff)
            
            if not tweets.exists():
                self.stdout.write(
                    self.style.WARNING('No tweets found in the last 24 hours')
                )
                return
            
            self.stdout.write(f'Found {tweets.count()} tweets to analyze')
            
            # Convert to list of dicts
            tweet_list = []
            for tweet in tweets:
                tweet_list.append({
                    'content': tweet.content,
                    'likes': tweet.likes,
                    'retweets': tweet.retweets,
                    'replies': tweet.replies,
                    'mentions': tweet.mentions,
                    'hashtags': tweet.hashtags,
                })
            
            # Initialize analyzer
            self.stdout.write('Fitting analyzer on tweet texts...')
            analyzer = TweetAnalyzer()
            texts = [t['content'] for t in tweet_list]
            analyzer.fit(texts)
            
            # Analyze tweets
            self.stdout.write('Generating trading signals...')
            analyses = analyzer.analyze_batch(tweet_list)
            
            # Save signals to database
            self.stdout.write('Saving signals to database...')
            saved_count = 0
            for tweet, analysis in zip(tweets, analyses):
                try:
                    TweetSignal.objects.update_or_create(
                        tweet=tweet,
                        defaults={
                            'tfidf_vector': analysis.get('tfidf_vector', {}),
                            'sentiment_score': analysis.get('sentiment_score'),
                            'sentiment_label': analysis.get('sentiment_label'),
                            'engagement_score': analysis.get('engagement_score'),
                            'custom_features': analysis.get('custom_features', {}),
                            'composite_signal': analysis.get('composite_signal'),
                        }
                    )
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"Error saving signal: {e}")
                    continue
            
            # Aggregate signals
            aggregated = analyzer.aggregate_signals(analyses)
            signals = [a.get('composite_signal', 0) for a in analyses]
            if signals:
                lower, upper = analyzer.calculate_confidence_interval(signals)
                aggregated['confidence_interval_lower'] = lower
                aggregated['confidence_interval_upper'] = upper
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully analyzed {saved_count} tweets!'
                )
            )
            self.stdout.write(f"Mean Signal: {aggregated.get('mean_signal', 0):.3f}")
            self.stdout.write(f"Mean Sentiment: {aggregated.get('mean_sentiment', 0):.3f}")
            self.stdout.write(f"Confidence Interval: [{aggregated.get('confidence_interval_lower', 0):.3f}, {aggregated.get('confidence_interval_upper', 0):.3f}]")
            
        except Exception as e:
            logger.error(f"Error analyzing tweets: {e}")
            self.stdout.write(
                self.style.ERROR(f'Error during analysis: {e}')
            )

