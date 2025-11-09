import logging
import pandas as pd
from django.db.models import Count, Avg, StdDev
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from ..models import Tweet, TweetSignal
from ..serializers import (
    GenerateVisualizationsResponseSerializer,
    ErrorResponseSerializer,
)
from ..services import (
    TweetAnalyzer,
    MemoryEfficientVisualizer,
)

logger = logging.getLogger(__name__)


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

