"""
Twitter scraper using Twikit library (no API key required)
Based on: https://github.com/d60/twikit
Reference: https://github.com/mehranshakarami/AI_Spectrum/tree/main/2024/Twikit
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
import time
from django.conf import settings

logger = logging.getLogger(__name__)

# Check if Twikit is available
try:
    from twikit import Client
    TWIKIT_AVAILABLE = True
except ImportError:
    TWIKIT_AVAILABLE = False
    Client = None

# Import TwitterScraper for factory function (lazy import to avoid circular dependencies)
try:
    from .twitter_scraper import TwitterScraper
except ImportError:
    TwitterScraper = None


class TwitterScraperTwikit:
    """Twitter scraper using Twikit library (no API key required)"""
    
    HASHTAGS = ['#nifty50', '#sensex', '#intraday', '#banknifty']
    MIN_TWEETS = 2000
    TIME_WINDOW_HOURS = getattr(settings, 'TWITTER_TIME_WINDOW_HOURS', 240)  # Can search further back with Twikit
    
    def __init__(self, max_workers: int = 3, username: str = None, password: str = None):
        """
        Initialize the Twikit scraper
        
        Args:
            max_workers: Number of concurrent workers (for future use)
            username: Optional Twitter username for authentication (improves rate limits)
            password: Optional Twitter password for authentication
        """
        if Client is None:
            raise ImportError(
                "Twikit library not installed. Install it with: pip install twikit"
            )
        
        self.max_workers = max_workers
        self.client = Client()
        self.authenticated = False
        self.username = username or getattr(settings, 'TWITTER_USERNAME', None)
        self.password = password or getattr(settings, 'TWITTER_PASSWORD', None)
    
    async def _authenticate(self):
        """Authenticate with Twitter (optional but recommended)"""
        try:
            await self.client.login(
                auth_info_1=self.username,
                auth_info_2=self.password
            )
            self.authenticated = True
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise
    
    async def _ensure_authenticated(self):
        """Ensure client is authenticated if credentials are available"""
        if not self.authenticated and self.username and self.password:
            try:
                await self._authenticate()
            except Exception as e:
                logger.warning(f"Authentication failed: {e}")
    
    async def _search_tweets_async(self, query: str, count: int = 100) -> List[Dict]:
        """
        Search tweets asynchronously using Twikit
        
        Args:
            query: Search query (hashtag, keyword, etc.)
            count: Number of tweets to retrieve
            
        Returns:
            List of tweet dictionaries
        """
        tweets = []
        try:
            await self._ensure_authenticated()
            search_results = await self.client.search_tweet(query, product='Latest', count=count)
            
            if not search_results:
                return tweets
            
            for tweet in search_results:
                try:
                    tweet_data = self._process_tweet_data(tweet)
                    if tweet_data and self._is_recent_tweet(tweet_data['timestamp']):
                        tweets.append(tweet_data)
                except Exception as e:
                    continue
            
        except Exception as e:
            logger.error(f"Error searching tweets: {e}")
        
        return tweets
    
    def _process_tweet_data(self, tweet) -> Optional[Dict]:
        """Process Twikit tweet object into our format"""
        try:
            # Extract tweet content
            content = tweet.full_text if hasattr(tweet, 'full_text') else (
                tweet.text if hasattr(tweet, 'text') else str(tweet)
            )
            
            # Extract username
            username = tweet.user.screen_name if hasattr(tweet, 'user') and hasattr(tweet.user, 'screen_name') else 'unknown'
            
            # Extract timestamp
            if hasattr(tweet, 'created_at'):
                timestamp = tweet.created_at
                if isinstance(timestamp, str):
                    # Parse timestamp string if needed
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                timestamp = datetime.now()
            
            # Extract metrics
            retweets = tweet.retweet_count if hasattr(tweet, 'retweet_count') else 0
            likes = tweet.favorite_count if hasattr(tweet, 'favorite_count') else (
                tweet.like_count if hasattr(tweet, 'like_count') else 0
            )
            replies = tweet.reply_count if hasattr(tweet, 'reply_count') else 0
            
            # Extract hashtags and mentions
            hashtags = re.findall(r'#(\w+)', content, re.IGNORECASE)
            mentions = re.findall(r'@(\w+)', content)
            
            return {
                'username': username,
                'timestamp': timestamp,
                'content': content,
                'retweets': retweets,
                'likes': likes,
                'replies': replies,
                'hashtags': hashtags,
                'mentions': mentions,
                'url': f"https://twitter.com/{username}/status/{tweet.id}" if hasattr(tweet, 'id') else None
            }
        except Exception as e:
            logger.warning(f"Error processing tweet data: {e}")
            return None
    
    def _is_recent_tweet(self, timestamp: datetime) -> bool:
        """Check if tweet is within the configured time window"""
        cutoff = datetime.now() - timedelta(hours=self.TIME_WINDOW_HOURS)
        return timestamp >= cutoff
    
    async def _scrape_hashtag_async(self, hashtag: str) -> List[Dict]:
        """Scrape tweets for a single hashtag asynchronously"""
        # Try multiple query formats
        queries = [
            hashtag,  # Direct hashtag
            f"{hashtag} lang:en",  # English only
            f'"{hashtag}"',  # Exact phrase
        ]
        
        all_tweets = []
        for query in queries:
            try:
                tweets = await self._search_tweets_async(query, count=500)
                if tweets:
                    all_tweets.extend(tweets)
                    break
            except Exception:
                continue
        
        seen = set()
        unique_tweets = []
        for tweet in all_tweets:
            content_hash = hash(tweet['content'])
            if content_hash not in seen:
                seen.add(content_hash)
                unique_tweets.append(tweet)
        
        logger.info(f"Collected {len(unique_tweets)} tweets for {hashtag}")
        return unique_tweets
    
    async def scrape_all_hashtags_async(self) -> List[Dict]:
        """Scrape all hashtags concurrently"""
        tasks = [self._scrape_hashtag_async(hashtag) for hashtag in self.HASHTAGS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_tweets = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error scraping {self.HASHTAGS[i]}: {result}")
            else:
                all_tweets.extend(result)
        
        logger.info(f"Collected {len(all_tweets)} unique tweets")
        return all_tweets
    
    def scrape_hashtag(self, hashtag: str) -> List[Dict]:
        """Synchronous wrapper for scraping a single hashtag"""
        return asyncio.run(self._scrape_hashtag_async(hashtag))
    
    def scrape_all_hashtags(self) -> List[Dict]:
        """Synchronous wrapper for scraping all hashtags"""
        return asyncio.run(self.scrape_all_hashtags_async())


# Factory function to choose scraper based on availability
def create_twitter_scraper(use_twikit: bool = None, **kwargs) -> object:
    """
    Factory function to create appropriate Twitter scraper
    
    Args:
        use_twikit: If True, use Twikit. If False, use API. If None, auto-detect
        **kwargs: Arguments to pass to scraper
        
    Returns:
        TwitterScraper or TwitterScraperTwikit instance
    """
    if use_twikit:
        return TwitterScraperTwikit(**kwargs)
    else:
        if TwitterScraper is None:
            raise ImportError("TwitterScraper could not be imported")
        return TwitterScraper(**kwargs)

