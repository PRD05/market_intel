"""
Twitter scraper using Twikit library (no API key required)
Based on: https://github.com/d60/twikit
Reference: https://github.com/mehranshakarami/AI_Spectrum/tree/main/2024/Twikit
"""
import asyncio
import logging
import re
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
import time

from market_intel.settings import bearer_token

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
    TIME_WINDOW_HOURS = int(os.environ.get('TWITTER_TIME_WINDOW_HOURS', '240'))  # Can search further back with Twikit
    
    def __init__(self, max_workers: int = 3, username: str = None, password: str = None):
        """
        Initialize the Twikit scraper
        
        Args:
            max_workers: Number of concurrent workers (for future use)
            username: Optional Twitter username for authentication (improves rate limits)
            password: Optional Twitter password for authentication
        """
        if not TWIKIT_AVAILABLE:
            raise ImportError(
                "Twikit library not installed. Install it with: pip install twikit\n"
                "Note: Twikit 2.0.0+ requires async/await syntax"
            )
        
        self.max_workers = max_workers
        self.client = Client()
        self.authenticated = False
        self.username = username or os.environ.get('TWITTER_USERNAME')
        self.password = password or os.environ.get('TWITTER_PASSWORD')
        
        logger.info("Twikit scraper initialized (no API key required)")
        
        # Note: Authentication will be done lazily on first request
        # This avoids blocking during initialization
        if self.username and self.password:
            logger.info("Credentials provided. Will authenticate on first request.")
        else:
            logger.info("No credentials provided. Using unauthenticated mode (may have stricter rate limits)")
    
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
                logger.info("Successfully authenticated with Twitter")
            except Exception as e:
                logger.warning(f"Authentication failed: {e}. Continuing without auth")
    
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
            # Ensure authenticated if credentials available
            await self._ensure_authenticated()
            
            logger.info(f"Searching tweets for query: {query}")
            
            # Search tweets using Twikit
            search_results = await self.client.search_tweet(query, product='Latest', count=count)
            
            if not search_results:
                logger.warning(f"No tweets found for query: {query}")
                return tweets
            
            logger.info(f"Found {len(search_results)} tweets for query: {query}")
            
            # Process each tweet
            for tweet in search_results:
                try:
                    tweet_data = self._process_tweet_data(tweet)
                    if tweet_data and self._is_recent_tweet(tweet_data['timestamp']):
                        tweets.append(tweet_data)
                except Exception as e:
                    logger.debug(f"Error processing tweet: {e}")
                    continue
            
            logger.info(f"Processed {len(tweets)} recent tweets for query: {query}")
            
        except Exception as e:
            logger.error(f"Error searching tweets for '{query}': {e}", exc_info=True)
        
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
        is_recent = timestamp >= cutoff
        if not is_recent:
            logger.debug(f"Tweet from {timestamp} is older than {self.TIME_WINDOW_HOURS} hours (cutoff: {cutoff})")
        return is_recent
    
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
                    logger.info(f"Found {len(tweets)} tweets with query: {query}")
                    all_tweets.extend(tweets)
                    break  # Use first successful query
                else:
                    logger.debug(f"No tweets found with query: {query}")
            except Exception as e:
                logger.debug(f"Query '{query}' failed: {e}")
                continue
        
        # Deduplicate by content hash
        seen = set()
        unique_tweets = []
        for tweet in all_tweets:
            content_hash = hash(tweet['content'])
            if content_hash not in seen:
                seen.add(content_hash)
                unique_tweets.append(tweet)
        
        logger.info(f"Collected {len(unique_tweets)} unique recent tweets for {hashtag}")
        return unique_tweets
    
    async def scrape_all_hashtags_async(self) -> List[Dict]:
        """Scrape all hashtags concurrently"""
        logger.info(f"Starting to scrape {len(self.HASHTAGS)} hashtags using Twikit...")
        
        # Scrape all hashtags concurrently
        tasks = [self._scrape_hashtag_async(hashtag) for hashtag in self.HASHTAGS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine all tweets
        all_tweets = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error scraping {self.HASHTAGS[i]}: {result}")
            else:
                all_tweets.extend(result)
        
        logger.info(f"Total unique tweets collected: {len(all_tweets)}")
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
        logger.info("✅ Using Twikit scraper (no API key required)")
        return TwitterScraperTwikit(**kwargs)
    else:
        if not bearer_token:
            raise Exception("Bearer token not provided")
        else:
            logger.info("✅ Using Twitter API v2 scraper (Bearer Token configured)")
        return TwitterScraper(**kwargs)

