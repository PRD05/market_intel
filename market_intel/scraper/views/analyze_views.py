import logging
from datetime import timedelta
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from ..models import Tweet, TweetSignal
from ..serializers import (
    AnalyzeTweetsFullResponseSerializer,
    ErrorResponseSerializer,
)
from ..services import TweetAnalyzer

logger = logging.getLogger(__name__)


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

