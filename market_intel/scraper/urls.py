from django.urls import path
from .views import (
    ScrapeTweetsAPIView,
    AnalyzeTweetsAPIView,
    GenerateVisualizationsAPIView,
    GetStatsAPIView,
)

urlpatterns = [
    path("scrape/", ScrapeTweetsAPIView.as_view(), name="scrape-tweets"),
    path("analyze/", AnalyzeTweetsAPIView.as_view(), name="analyze-tweets"),
    path("visualize/", GenerateVisualizationsAPIView.as_view(), name="generate-visualizations"),
    path("stats/", GetStatsAPIView.as_view(), name="get-stats"),
]
