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
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import Tweet, TweetSignal, ScrapingSession
from .serializers import (
    ScrapeTweetsRequestSerializer,
    ScrapeTweetsResponseSerializer,
    AnalyzeTweetsFullResponseSerializer,
    ErrorResponseSerializer,
    GenerateVisualizationsResponseSerializer,
    GetStatsResponseSerializer,
)
from .twitter_scraper import TwitterScraper
from .twitter_scraper_twikit import create_twitter_scraper
from .data_processor import DataProcessor
from .analyzer import TweetAnalyzer
from .visualizer import MemoryEfficientVisualizer
import json

logger = logging.getLogger(__name__)


class ScrapeTweetsAPIView(APIView):
    """API endpoint to scrape tweets"""
    
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
            logger.info(f"📥 Received scrape request with use_twikit={use_twikit}")
            logger.info(f"   Request data: {request.data if hasattr(request, 'data') else 'N/A'}")
            
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
    
    def _scrape_and_process(self, session_id: int, use_twikit: bool = None):
        """Background task to scrape and process tweets"""
        session = None
        try:
            session = ScrapingSession.objects.get(id=session_id)
            
            # Initialize components
            # Use Twikit if available (no API key required), otherwise use Twitter API
            logger.info(f"Creating scraper with use_twikit={use_twikit}")
            scraper = create_twitter_scraper(use_twikit=use_twikit, max_workers=3)
            logger.info(f"Scraper created: {type(scraper).__name__}")
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
    
    @swagger_auto_schema(
        operation_description="Analyze collected tweets and generate trading signals based on sentiment and engagement. "
                              "Use query parameters to filter tweets by time window and limit the number analyzed.",
        manual_parameters=[
            openapi.Parameter(
                'hours',
                openapi.IN_QUERY,
                description="Number of hours to look back. Use '0' or 'all' to analyze all tweets. Default: 24",
                type=openapi.TYPE_STRING,
                default='24',
                required=False
            ),
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description="Maximum number of tweets to analyze. If not specified, analyzes all matching tweets.",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
        ],
        responses={
            200: AnalyzeTweetsFullResponseSerializer,
            400: ErrorResponseSerializer,
        },
        tags=['Analysis']
    )
    def post(self, request):
        """Analyze tweets and generate trading signals
        
        Query parameters:
        - hours: Number of hours to look back (default: 24, use 0 or 'all' for all tweets)
        - limit: Maximum number of tweets to analyze (default: no limit)
        """
        try:
            from datetime import timedelta
            
            # Get query parameters
            hours_param = request.query_params.get('hours', '24')
            limit_param = request.query_params.get('limit', None)
            
            # Determine time filter
            if hours_param in ['0', 'all', '']:
                # Analyze all tweets
                tweets = Tweet.objects.all()
            else:
                try:
                    hours = int(hours_param)
                    cutoff = timezone.now() - timedelta(hours=hours)
                    tweets = Tweet.objects.filter(timestamp__gte=cutoff)
                except ValueError:
                    return Response({
                        'error': f'Invalid hours parameter: {hours_param}. Use a number, 0, or "all"'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Apply limit if specified
            if limit_param:
                try:
                    limit = int(limit_param)
                    tweets = tweets[:limit]
                except ValueError:
                    return Response({
                        'error': f'Invalid limit parameter: {limit_param}. Must be a number'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Convert to queryset list to check existence
            tweets_list = list(tweets)
            
            if not tweets_list:
                total_tweets = Tweet.objects.count()
                return Response({
                    'error': f'No tweets found matching the criteria',
                    'total_tweets_in_db': total_tweets,
                    'suggestion': 'Try using ?hours=0 or ?hours=all to analyze all tweets, or scrape new tweets first'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Convert to list of dicts
            tweet_list = []
            for tweet in tweets_list:
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
            for tweet, analysis in zip(tweets_list, analyses):
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
                'total_tweets_processed': len(tweets_list),
                'aggregated_signals': aggregated
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error analyzing tweets: {e}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GenerateVisualizationsAPIView(APIView):
    """API endpoint to generate visualizations"""
    
    @swagger_auto_schema(
        operation_description="Generate visualizations from analyzed tweets. Creates charts showing signal trends, "
                              "sentiment distribution, engagement metrics, and signal aggregation. "
                              "Requires tweets to be analyzed first using /api/analyze/ endpoint.",
        responses={
            200: GenerateVisualizationsResponseSerializer,
            400: ErrorResponseSerializer,
        },
        tags=['Visualization']
    )
    def post(self, request):
        """Generate all visualizations"""
        try:
            # Get tweets with signals
            tweets_with_signals = Tweet.objects.filter(signal__isnull=False).select_related('signal')
            
            if not tweets_with_signals.exists():
                return Response({
                    'error': 'No tweets with signals found',
                    'suggestion': 'Run /api/analyze/ first to generate signals from tweets'
                }, status=status.HTTP_400_BAD_REQUEST)
            
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
    
    @swagger_auto_schema(
        operation_description="Get statistics about collected tweets and generated signals. "
                              "Returns counts, engagement metrics, and recent activity statistics.",
        responses={
            200: GetStatsResponseSerializer,
        },
        tags=['Statistics']
    )
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

