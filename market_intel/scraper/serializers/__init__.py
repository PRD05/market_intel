"""
Serializers package for API request/response models
Used for Swagger/OpenAPI documentation and validation
"""
from .scrape import (
    ScrapeTweetsRequestSerializer,
    ScrapeTweetsResponseSerializer,
)
from .analyze import (
    AnalyzeTweetsResponseSerializer,
    AnalyzeTweetsFullResponseSerializer,
    AggregatedSignalsSerializer,
    SentimentDistributionSerializer,
)
from .visualization import (
    GenerateVisualizationsResponseSerializer,
    PlotPathsSerializer,
)
from .stats import (
    GetStatsResponseSerializer,
    EngagementStatsSerializer,
    SignalStatsSerializer,
)
from .common import (
    ErrorResponseSerializer,
)

__all__ = [
    # Scrape serializers
    'ScrapeTweetsRequestSerializer',
    'ScrapeTweetsResponseSerializer',
    # Analyze serializers
    'AnalyzeTweetsResponseSerializer',
    'AnalyzeTweetsFullResponseSerializer',
    'AggregatedSignalsSerializer',
    'SentimentDistributionSerializer',
    # Visualization serializers
    'GenerateVisualizationsResponseSerializer',
    'PlotPathsSerializer',
    # Stats serializers
    'GetStatsResponseSerializer',
    'EngagementStatsSerializer',
    'SignalStatsSerializer',
    # Common serializers
    'ErrorResponseSerializer',
]

