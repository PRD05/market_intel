"""
Serializers for scraping endpoints
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

