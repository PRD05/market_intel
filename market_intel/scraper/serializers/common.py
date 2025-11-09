"""
Common serializers used across multiple endpoints
"""
from rest_framework import serializers


class ErrorResponseSerializer(serializers.Serializer):
    """Error response serializer"""
    error = serializers.CharField(help_text="Error message")
    total_tweets_in_db = serializers.IntegerField(required=False, help_text="Total tweets in database")
    suggestion = serializers.CharField(required=False, help_text="Suggestion to resolve the error")

