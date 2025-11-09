from django.db import models
from .tweet import Tweet


class TweetSignal(models.Model):
    """Model to store processed signals from tweets"""
    tweet = models.OneToOneField(Tweet, on_delete=models.CASCADE, related_name='signal')
    
    # TF-IDF features (stored as JSON)
    tfidf_vector = models.JSONField(default=dict, blank=True)
    
    # Sentiment scores
    sentiment_score = models.FloatField(null=True, blank=True)
    sentiment_label = models.CharField(max_length=20, null=True, blank=True)
    
    # Engagement score
    engagement_score = models.FloatField(default=0.0)
    
    # Custom features
    custom_features = models.JSONField(default=dict, blank=True)
    
    # Composite signal
    composite_signal = models.FloatField(null=True, blank=True)
    confidence_interval_lower = models.FloatField(null=True, blank=True)
    confidence_interval_upper = models.FloatField(null=True, blank=True)
    
    processed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-processed_at']
        indexes = [
            models.Index(fields=['-composite_signal']),
            models.Index(fields=['sentiment_score']),
        ]

    def __str__(self):
        return f"Signal for Tweet {self.tweet.id}"

