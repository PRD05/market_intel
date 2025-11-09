"""
Serializers for statistics endpoints
"""
from rest_framework import serializers


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

