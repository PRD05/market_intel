from django.urls import path
from . import views

urlpatterns = [
    path("scrape/", views.ScrapeTweetsAPIView.as_view(), name="scrape-tweets"),
    path("analyze/", views.AnalyzeTweetsAPIView.as_view(), name="analyze-tweets"),
    path("visualize/", views.GenerateVisualizationsAPIView.as_view(), name="generate-visualizations"),
    path("stats/", views.GetStatsAPIView.as_view(), name="get-stats"),
]
