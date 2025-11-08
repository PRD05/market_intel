from django.contrib import admin
from .models import Tweet, TweetSignal, ScrapingSession


@admin.register(Tweet)
class TweetAdmin(admin.ModelAdmin):
    list_display = ['username', 'timestamp', 'content_preview', 'likes', 'retweets', 'scraped_at']
    list_filter = ['timestamp', 'scraped_at']
    search_fields = ['username', 'content']
    readonly_fields = ['scraped_at']
    
    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Content'


@admin.register(TweetSignal)
class TweetSignalAdmin(admin.ModelAdmin):
    list_display = ['tweet', 'sentiment_score', 'engagement_score', 'composite_signal', 'processed_at']
    list_filter = ['sentiment_label', 'processed_at']
    search_fields = ['tweet__username', 'tweet__content']


@admin.register(ScrapingSession)
class ScrapingSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'started_at', 'completed_at', 'status', 'tweets_collected']
    list_filter = ['status', 'started_at']
    readonly_fields = ['started_at']
