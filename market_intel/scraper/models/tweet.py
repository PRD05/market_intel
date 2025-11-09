from django.db import models


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

