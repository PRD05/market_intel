"""
Serializers for analysis endpoints
"""
from rest_framework import serializers


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


class AnalyzeTweetsResponseSerializer(serializers.Serializer):
    """Response serializer for analyzing tweets"""
    status = serializers.CharField(help_text="Status of the analysis")
    tweets_analyzed = serializers.IntegerField(help_text="Number of tweets analyzed")
    total_tweets_processed = serializers.IntegerField(help_text="Total tweets processed")
    
    # Aggregated signals nested serializer - flexible dict with mixed types
    aggregated_signals = serializers.DictField(
        help_text="Aggregated signal statistics (can contain numbers, strings, nested objects)"
    )


class AnalyzeTweetsFullResponseSerializer(serializers.Serializer):
    """Full response serializer for analyzing tweets"""
    status = serializers.CharField(help_text="Status of the analysis")
    tweets_analyzed = serializers.IntegerField(help_text="Number of tweets analyzed and saved")
    total_tweets_processed = serializers.IntegerField(help_text="Total tweets processed")
    aggregated_signals = AggregatedSignalsSerializer(help_text="Aggregated signal statistics")

