from django.db import models
from django.utils import timezone


class Tweet(models.Model):
    """Model to store scraped tweets"""
    username = models.CharField(max_length=255)
    timestamp = models.DateTimeField()
    content = models.TextField()
    likes = models.IntegerField(default=0)
    retweets = models.IntegerField(default=0)
    replies = models.IntegerField(default=0)
    mentions = models.JSONField(default=list, blank=True)
    hashtags = models.JSONField(default=list, blank=True)
    tweet_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    url = models.URLField(max_length=500, null=True, blank=True)
    scraped_at = models.DateTimeField(auto_now_add=True)
    
    # For deduplication
    content_hash = models.CharField(max_length=64, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['content_hash']),
            models.Index(fields=['username']),
        ]

    def __str__(self):
        return f"{self.username} - {self.timestamp}"


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


class ScrapingSession(models.Model):
    """Model to track scraping sessions"""
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='running'
    )
    tweets_collected = models.IntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    
    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Session {self.id} - {self.status}"
