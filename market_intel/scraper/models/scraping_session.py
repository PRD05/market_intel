from django.db import models


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

