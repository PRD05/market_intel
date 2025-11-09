"""
Serializers for API request/response models
Used for Swagger/OpenAPI documentation and validation
"""
from rest_framework import serializers


class ScrapeTweetsRequestSerializer(serializers.Serializer):
    """Request serializer for scraping tweets"""
    use_twikit = serializers.BooleanField(
        required=False,
        allow_null=True,
        help_text="If True, use Twikit scraper (no API key required). "
                 "If False, use Twitter API. If not specified, auto-detect based on available credentials."
    )


class ScrapeTweetsResponseSerializer(serializers.Serializer):
    """Response serializer for scraping tweets"""
    status = serializers.CharField(help_text="Status of the scraping operation")
    session_id = serializers.IntegerField(help_text="Session ID to track scraping progress")
    message = serializers.CharField(help_text="Status message")
    scraper = serializers.CharField(help_text="Scraper type used")


class AnalyzeTweetsResponseSerializer(serializers.Serializer):
    """Response serializer for analyzing tweets"""
    status = serializers.CharField(help_text="Status of the analysis")
    tweets_analyzed = serializers.IntegerField(help_text="Number of tweets analyzed")
    total_tweets_processed = serializers.IntegerField(help_text="Total tweets processed")
    
    # Aggregated signals nested serializer - flexible dict with mixed types
    aggregated_signals = serializers.DictField(
        help_text="Aggregated signal statistics (can contain numbers, strings, nested objects)"
    )


class SentimentDistributionSerializer(serializers.Serializer):
    """Serializer for sentiment distribution"""
    positive = serializers.IntegerField(help_text="Number of positive tweets")
    negative = serializers.IntegerField(help_text="Number of negative tweets")
    neutral = serializers.IntegerField(help_text="Number of neutral tweets")


class AggregatedSignalsSerializer(serializers.Serializer):
    """Serializer for aggregated signals"""
    mean_signal = serializers.FloatField(help_text="Mean composite signal")
    std_signal = serializers.FloatField(help_text="Standard deviation of signals")
    confidence_interval_lower = serializers.FloatField(help_text="Lower confidence interval")
    confidence_interval_upper = serializers.FloatField(help_text="Upper confidence interval")
    mean_sentiment = serializers.FloatField(help_text="Mean sentiment score")
    mean_engagement = serializers.FloatField(help_text="Mean engagement score")
    total_tweets = serializers.IntegerField(help_text="Total number of tweets")
    sentiment_distribution = SentimentDistributionSerializer(help_text="Sentiment distribution")


class AnalyzeTweetsFullResponseSerializer(serializers.Serializer):
    """Full response serializer for analyzing tweets"""
    status = serializers.CharField(help_text="Status of the analysis")
    tweets_analyzed = serializers.IntegerField(help_text="Number of tweets analyzed and saved")
    total_tweets_processed = serializers.IntegerField(help_text="Total tweets processed")
    aggregated_signals = AggregatedSignalsSerializer(help_text="Aggregated signal statistics")


class ErrorResponseSerializer(serializers.Serializer):
    """Error response serializer"""
    error = serializers.CharField(help_text="Error message")
    total_tweets_in_db = serializers.IntegerField(required=False, help_text="Total tweets in database")
    suggestion = serializers.CharField(required=False, help_text="Suggestion to resolve the error")


class PlotPathsSerializer(serializers.Serializer):
    """Serializer for visualization plot paths"""
    signal_over_time = serializers.CharField(help_text="Path to signal over time plot")
    sentiment_distribution = serializers.CharField(help_text="Path to sentiment distribution plot")
    engagement_vs_sentiment = serializers.CharField(help_text="Path to engagement vs sentiment plot")
    signal_aggregation = serializers.CharField(help_text="Path to signal aggregation plot")


class GenerateVisualizationsResponseSerializer(serializers.Serializer):
    """Response serializer for generating visualizations"""
    status = serializers.CharField(help_text="Status of visualization generation")
    plots = PlotPathsSerializer(help_text="Paths to generated visualization plots")
    aggregated_signals = serializers.DictField(
        help_text="Aggregated signal statistics (can contain numbers, strings, nested objects)"
    )


class EngagementStatsSerializer(serializers.Serializer):
    """Serializer for engagement statistics"""
    avg_likes = serializers.FloatField(help_text="Average likes per tweet")
    avg_retweets = serializers.FloatField(help_text="Average retweets per tweet")
    max_likes = serializers.IntegerField(help_text="Maximum likes on a single tweet")


class SignalStatsSerializer(serializers.Serializer):
    """Serializer for signal statistics"""
    avg_signal = serializers.FloatField(help_text="Average composite signal")
    avg_sentiment = serializers.FloatField(help_text="Average sentiment score")
    avg_engagement = serializers.FloatField(help_text="Average engagement score")


class GetStatsResponseSerializer(serializers.Serializer):
    """Response serializer for statistics"""
    total_tweets = serializers.IntegerField(help_text="Total number of tweets in database")
    total_signals = serializers.IntegerField(help_text="Total number of tweets with signals")
    recent_tweets_24h = serializers.IntegerField(help_text="Number of tweets in last 24 hours")
    engagement_stats = EngagementStatsSerializer(help_text="Engagement statistics")
    signal_stats = SignalStatsSerializer(help_text="Signal and sentiment statistics")
    top_hashtags = serializers.DictField(
        help_text="Top 10 hashtags by frequency",
        child=serializers.IntegerField(),
        required=False
    )

