import logging
import threading
import pandas as pd
from django.http import JsonResponse
from django.views import View
from django.utils import timezone
from django.db import transaction, models
from django.db.models import Count, Avg, Max, Min, StdDev
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Tweet, TweetSignal, ScrapingSession
from .twitter_scraper import TwitterScraper
from .data_processor import DataProcessor
from .analyzer import TweetAnalyzer
from .visualizer import MemoryEfficientVisualizer
import json

logger = logging.getLogger(__name__)


class ScrapeTweetsAPIView(APIView):
    """API endpoint to scrape tweets"""
    
    def post(self, request):
        """Start scraping process"""
        try:
            # Create scraping session
            session = ScrapingSession.objects.create(status='running')
            
            # Start scraping in background thread
            thread = threading.Thread(
                target=self._scrape_and_process,
                args=(session.id,),
                daemon=True
            )
            thread.start()
            
            return Response({
                'status': 'started',
                'session_id': session.id,
                'message': 'Scraping started in background'
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Error starting scrape: {e}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _scrape_and_process(self, session_id: int):
        """Background task to scrape and process tweets"""
        session = None
        try:
            session = ScrapingSession.objects.get(id=session_id)
            
            # Initialize components
            scraper = TwitterScraper(headless=True, max_workers=3)
            processor = DataProcessor(output_dir="data")
            
            # Scrape tweets
            logger.info("Starting tweet scraping...")
            raw_tweets = scraper.scrape_all_hashtags()
            
            if len(raw_tweets) < 2000:
                logger.warning(f"Only collected {len(raw_tweets)} tweets, less than minimum 2000")
            
            # Process tweets
            logger.info("Processing tweets...")
            processed_tweets = processor.process_tweets(raw_tweets)
            
            # Deduplicate
            processed_tweets = processor.deduplicate(processed_tweets)
            
            # Save to database
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


class AnalyzeTweetsAPIView(APIView):
    """API endpoint to analyze tweets and generate signals"""
    
    def post(self, request):
        """Analyze tweets and generate trading signals"""
        try:
            # Get tweets from last 24 hours
            from datetime import timedelta
            cutoff = timezone.now() - timedelta(hours=24)
            tweets = Tweet.objects.filter(timestamp__gte=cutoff)
            
            if not tweets.exists():
                return Response({
                    'error': 'No tweets found in the last 24 hours'
                }, status=status.HTTP_404_NOT_FOUND)
            
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
            analyzer = TweetAnalyzer()
            
            # Fit on all tweet texts
            texts = [t['content'] for t in tweet_list]
            analyzer.fit(texts)
            
            # Analyze tweets
            analyses = analyzer.analyze_batch(tweet_list)
            
            # Save signals to database
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
            
            # Update confidence intervals
            signals = [a.get('composite_signal', 0) for a in analyses]
            if signals:
                lower, upper = analyzer.calculate_confidence_interval(signals)
                aggregated['confidence_interval_lower'] = lower
                aggregated['confidence_interval_upper'] = upper
            
            return Response({
                'status': 'success',
                'tweets_analyzed': saved_count,
                'aggregated_signals': aggregated
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error analyzing tweets: {e}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GenerateVisualizationsAPIView(APIView):
    """API endpoint to generate visualizations"""
    
    def post(self, request):
        """Generate all visualizations"""
        try:
            # Get tweets with signals
            tweets_with_signals = Tweet.objects.filter(signal__isnull=False).select_related('signal')
            
            if not tweets_with_signals.exists():
                return Response({
                    'error': 'No tweets with signals found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Prepare data
            data = []
            for tweet in tweets_with_signals:
                signal = tweet.signal
                data.append({
                    'timestamp': tweet.timestamp,
                    'composite_signal': signal.composite_signal or 0,
                    'sentiment_score': signal.sentiment_score or 0,
                    'sentiment_label': signal.sentiment_label or 'neutral',
                    'engagement_score': signal.engagement_score or 0,
                })
            
            df = pd.DataFrame(data)
            
            # Initialize visualizer
            visualizer = MemoryEfficientVisualizer()
            
            # Generate plots
            plots = {}
            plots['signal_over_time'] = visualizer.plot_signal_over_time(df)
            plots['sentiment_distribution'] = visualizer.plot_sentiment_distribution(df)
            plots['engagement_vs_sentiment'] = visualizer.plot_engagement_vs_sentiment(df)
            
            # Get aggregated signals for aggregation plot
            signals = TweetSignal.objects.all()
            signal_agg = signals.aggregate(
                avg_signal=Avg('composite_signal'),
                std_signal=StdDev('composite_signal'),
                avg_sentiment=Avg('sentiment_score'),
                avg_engagement=Avg('engagement_score'),
            )
            aggregated = {
                'mean_signal': float(signal_agg['avg_signal'] or 0),
                'std_signal': float(signal_agg['std_signal'] or 0),
                'mean_sentiment': float(signal_agg['avg_sentiment'] or 0),
                'mean_engagement': float(signal_agg['avg_engagement'] or 0),
                'total_tweets': signals.count(),
                'sentiment_distribution': dict(signals.values_list('sentiment_label').annotate(count=Count('id'))),
            }
            
            # Calculate confidence interval
            signal_values = list(signals.values_list('composite_signal', flat=True))
            if signal_values:
                from .analyzer import TweetAnalyzer
                analyzer = TweetAnalyzer()
                lower, upper = analyzer.calculate_confidence_interval(signal_values)
                aggregated['confidence_interval_lower'] = lower
                aggregated['confidence_interval_upper'] = upper
            
            plots['signal_aggregation'] = visualizer.plot_signal_aggregation(aggregated)
            
            return Response({
                'status': 'success',
                'plots': plots,
                'aggregated_signals': aggregated
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error generating visualizations: {e}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetStatsAPIView(APIView):
    """API endpoint to get statistics"""
    
    def get(self, request):
        """Get statistics about collected tweets and signals"""
        try:
            from datetime import timedelta
            
            # Overall stats
            total_tweets = Tweet.objects.count()
            total_signals = TweetSignal.objects.count()
            
            # Last 24 hours
            cutoff = timezone.now() - timedelta(hours=24)
            recent_tweets = Tweet.objects.filter(timestamp__gte=cutoff).count()
            
            # Engagement stats
            engagement_stats = Tweet.objects.aggregate(
                avg_likes=Avg('likes'),
                avg_retweets=Avg('retweets'),
                max_likes=Max('likes'),
            )
            
            # Signal stats
            signal_stats = TweetSignal.objects.aggregate(
                avg_signal=Avg('composite_signal'),
                avg_sentiment=Avg('sentiment_score'),
                avg_engagement=Avg('engagement_score'),
            )
            
            # Hashtag distribution
            hashtag_counts = {}
            for tweet in Tweet.objects.all():
                for hashtag in tweet.hashtags:
                    hashtag_counts[hashtag] = hashtag_counts.get(hashtag, 0) + 1
            
            return Response({
                'total_tweets': total_tweets,
                'total_signals': total_signals,
                'recent_tweets_24h': recent_tweets,
                'engagement_stats': engagement_stats,
                'signal_stats': signal_stats,
                'top_hashtags': dict(sorted(hashtag_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

