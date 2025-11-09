"""
Serializers for visualization endpoints
"""
from rest_framework import serializers


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

