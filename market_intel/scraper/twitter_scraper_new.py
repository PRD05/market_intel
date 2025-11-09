"""
Twitter/X API v2 scraper using OAuth 2.0 Bearer Token for collecting Indian stock market tweets.
Uses official Twitter API with Academic Research access for comprehensive tweet search.
"""
import time
import hashlib
import logging
import re
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class TwitterScraper:
    """Twitter API v2 scraper using OAuth 2.0 Bearer Token"""

    HASHTAGS = ['#nifty50', '#sensex', '#intraday', '#banknifty']
    MIN_TWEETS = 2000
    TIME_WINDOW_HOURS = 240

    # Twitter API v2 configuration
    BASE_URL = "https://api.twitter.com/2"
    SEARCH_ENDPOINT = "/tweets/search/recent"  # Academic Research access required

    def __init__(self, max_workers: int = 3):
        """
        Initialize the Twitter API scraper

        Args:
            max_workers: Number of concurrent API requests (rate limited)
        """
        self.max_workers = max_workers
        self.bearer_token = os.environ.get('TWITTER_BEARER_TOKEN')
        self.session = requests.Session()

        # Set up session headers
        if self.bearer_token:
            self.session.headers.update({
                'Authorization': f'Bearer {self.bearer_token}',
                'Content-Type': 'application/json'
            })
            logger.info("Twitter Bearer Token configured")
        else:
            logger.error("TWITTER_BEARER_TOKEN environment variable not set")
            logger.error("Get your Bearer Token from: https://developer.twitter.com/en/portal/dashboard")
            logger.error("You'll need Academic Research access for full tweet search")

        # Rate limiting: Twitter API v2 allows 300 requests per 15 minutes for recent search
        self.requests_per_window = 300
        self.window_seconds = 900  # 15 minutes
        self.request_times = []

    def _rate_limit_check(self):
        """Check and enforce rate limiting"""
        now = time.time()

        # Remove old requests outside the window
        self.request_times = [t for t in self.request_times if now - t < self.window_seconds]

        if len(self.request_times) >= self.requests_per_window:
            # Calculate wait time
            oldest_request = min(self.request_times)
            wait_time = self.window_seconds - (now - oldest_request)
            if wait_time > 0:
                logger.info(f"Rate limit reached. Waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                self.request_times = []

        self.request_times.append(now)

    def _make_api_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make a rate-limited API request to Twitter"""
        if not self.bearer_token:
            raise ValueError("Twitter Bearer Token not configured")

        self._rate_limit_check()

        url = f"{self.BASE_URL}{endpoint}"
        logger.debug(f"Making API request to: {url}")

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()

            # Log rate limit info
            remaining = response.headers.get('x-rate-limit-remaining')
            reset_time = response.headers.get('x-rate-limit-reset')
            if remaining:
                logger.debug(f"Rate limit remaining: {remaining}")

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            if hasattr(e, 'response') and e.response:
                if e.response.status_code == 429:
                    logger.warning("Rate limit exceeded. Waiting before retry...")
                    time.sleep(60)  # Wait 1 minute on rate limit
                elif e.response.status_code == 401:
                    logger.error("Authentication failed. Check your Bearer Token.")
                elif e.response.status_code == 403:
                    logger.error("Access forbidden. You may need Academic Research access.")
            raise

    def _search_tweets(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search tweets using Twitter API v2

        Args:
            query: Twitter search query
            max_results: Maximum results per request (max 100)

        Returns:
            List of tweet dictionaries
        """
        tweets = []
        next_token = None

        while len(tweets) < max_results:
            params = {
                'query': query,
                'max_results': min(100, max_results - len(tweets)),
                'tweet.fields': 'created_at,public_metrics,author_id,lang,text',
                'user.fields': 'username,name',
                'expansions': 'author_id'
            }

            if next_token:
                params['next_token'] = next_token

            try:
                response = self._make_api_request(self.SEARCH_ENDPOINT, params)

                # Process tweets
                if 'data' in response:
                    for tweet in response['data']:
                        tweet_data = self._process_tweet_data(tweet, response.get('includes', {}))
                        if tweet_data:
                            tweets.append(tweet_data)

                # Check for next page
                meta = response.get('meta', {})
                if 'next_token' not in meta:
                    break
                next_token = meta['next_token']

                # Avoid infinite loops
                if len(tweets) >= max_results:
                    break

            except Exception as e:
                logger.error(f"Error searching tweets for query '{query}': {e}")
                break

        logger.info(f"Found {len(tweets)} tweets for query: {query}")
        return tweets[:max_results]

    def _process_tweet_data(self, tweet: Dict, includes: Dict) -> Optional[Dict]:
        """Process raw tweet data from API into our format"""
        try:
            # Get user info
            author_id = tweet.get('author_id')
            users = includes.get('users', [])
            user_info = next((u for u in users if u['id'] == author_id), {})

            # Extract metrics
            metrics = tweet.get('public_metrics', {})
            likes = metrics.get('like_count', 0)
            retweets = metrics.get('retweet_count', 0)
            replies = metrics.get('reply_count', 0)

            # Create content hash
            content = tweet.get('text', '')
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

            # Extract hashtags and mentions
            hashtags = re.findall(r'#(\w+)', content, re.IGNORECASE)
            mentions = re.findall(r'@(\w+)', content)

            # Convert timestamp
            created_at = tweet.get('created_at')
            if created_at:
                timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                timestamp = datetime.now()

            return {
                'username': user_info.get('username', 'unknown'),
                'timestamp': timestamp,
                'content': content,
                'likes': likes,
                'retweets': retweets,
                'replies': replies,
                'mentions': mentions,
                'hashtags': hashtags,
                'tweet_id': tweet.get('id'),
                'url': f"https://twitter.com/i/web/status/{tweet.get('id')}",
                'content_hash': content_hash,
            }

        except Exception as e:
            logger.warning(f"Error processing tweet data: {e}")
            return None

    def scrape_hashtag(self, hashtag: str) -> List[Dict]:
        """Scrape tweets for a single hashtag using Twitter API"""
        logger.info(f"Searching tweets for {hashtag} using Twitter API...")

        # Build search query
        query = f"{hashtag} lang:en"  # English tweets only
        tweets = self._search_tweets(query, max_results=500)

        # Filter for recent tweets
        recent_tweets = []
        for tweet in tweets:
            if self._is_recent_tweet(tweet['timestamp']):
                recent_tweets.append(tweet)

        logger.info(f"Collected {len(recent_tweets)} recent tweets for {hashtag}")
        return recent_tweets

    def _is_recent_tweet(self, timestamp: datetime) -> bool:
        """Check if tweet is within the configured time window"""
        cutoff = datetime.now() - timedelta(hours=self.TIME_WINDOW_HOURS)
        return timestamp >= cutoff

    def scrape_all_hashtags(self) -> List[Dict]:
        """
        Scrape all hashtags sequentially using Twitter API

        Returns:
            List of all unique tweets
        """
        all_tweets = []
        seen_hashes = set()

        # Process hashtags sequentially
        for hashtag in self.HASHTAGS:
            try:
                tweets = self.scrape_hashtag(hashtag)
                for tweet in tweets:
                    if tweet['content_hash'] not in seen_hashes:
                        seen_hashes.add(tweet['content_hash'])
                        all_tweets.append(tweet)
            except Exception as e:
                logger.error(f"Error processing {hashtag}: {e}")

        logger.info(f"Total unique tweets collected: {len(all_tweets)}")
        return all_tweets
