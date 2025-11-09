import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg, Max
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from ..models import Tweet, TweetSignal
from ..serializers import GetStatsResponseSerializer

logger = logging.getLogger(__name__)


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

