"""
Twitter/X API v2 scraper using OAuth 2.0 Bearer Token for collecting Indian stock market tweets.
Uses official Twitter API with Academic Research access for comprehensive tweet search.
"""
import time
import hashlib
import logging
import re
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class TwitterScraper:
    """Twitter API v2 scraper using OAuth 2.0 Bearer Token"""
    
    HASHTAGS = ['#nifty50', '#sensex', '#intraday', '#banknifty']
    MIN_TWEETS = 2000
    # Note: Standard API access allows 7 days (168 hours) max
    # Academic Research access allows full archive
    # Set to 168 for standard access, 240+ for Academic Research
    TIME_WINDOW_HOURS = getattr(settings, 'TWITTER_TIME_WINDOW_HOURS', 168)

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
        self.bearer_token = getattr(settings, 'TWITTER_BEARER_TOKEN', None)
        self.session = requests.Session()

        # Set up session headers
        if self.bearer_token:
            self.session.headers.update({
                'Authorization': f'Bearer {self.bearer_token}',
                'Content-Type': 'application/json'
            })
            if self.TIME_WINDOW_HOURS > 168:
                logger.warning(f"Time window {self.TIME_WINDOW_HOURS}h exceeds standard API limit (168h)")
        else:
            logger.error("TWITTER_BEARER_TOKEN not set")

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
            logger.error("Twitter Bearer Token not configured")
            raise ValueError("Twitter Bearer Token not configured")

        self._rate_limit_check()

        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response:
                status_code = e.response.status_code
                if status_code == 429:
                    logger.warning("Rate limit exceeded")
                    time.sleep(60)
                elif status_code == 401:
                    logger.error("Authentication failed")
                elif status_code == 403:
                    logger.error("Access forbidden - may need Academic Research access")
                elif status_code == 400:
                    logger.error("Bad request")
            logger.error(f"API request failed: {e}")
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

                if 'errors' in response:
                    for error in response['errors']:
                        logger.error(f"API error: {error.get('message')}")

                if 'data' in response and response['data']:
                    for tweet in response['data']:
                        tweet_data = self._process_tweet_data(tweet, response.get('includes', {}))
                        if tweet_data:
                            tweets.append(tweet_data)

                meta = response.get('meta', {})
                if 'next_token' not in meta:
                    break
                next_token = meta['next_token']

                # Avoid infinite loops
                if len(tweets) >= max_results:
                    break

            except Exception as e:
                logger.error(f"Error searching tweets: {e}")
                break

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
        queries = [
            f"{hashtag} lang:en",
            f"{hashtag}",
            f'"{hashtag}"',
        ]

        all_tweets = []
        for query in queries:
            tweets = self._search_tweets(query, max_results=500)
            if tweets:
                all_tweets.extend(tweets)
                break

        recent_tweets = [t for t in all_tweets if self._is_recent_tweet(t['timestamp'])]
        logger.info(f"Collected {len(recent_tweets)} tweets for {hashtag}")
        return recent_tweets
    
    def _is_recent_tweet(self, timestamp: datetime) -> bool:
        """Check if tweet is within the configured time window"""
        cutoff = datetime.now() - timedelta(hours=self.TIME_WINDOW_HOURS)
        return timestamp >= cutoff

    def test_api_connection(self) -> Dict:
        """
        Test API connection and return diagnostic information
        
        Returns:
            Dictionary with connection status and diagnostic info
        """
        diagnostics = {
            'bearer_token_configured': bool(self.bearer_token),
            'api_accessible': False,
            'error': None,
            'rate_limit_info': None,
            'test_query_result': None
        }

        if not self.bearer_token:
            diagnostics['error'] = "Bearer Token not configured"
            return diagnostics

        try:
            # Test with a simple query
            test_query = "#nifty50"
            params = {
                'query': test_query,
                'max_results': 10,
                'tweet.fields': 'created_at,text',
                'user.fields': 'username'
            }

            # Make direct request to capture headers
            self._rate_limit_check()
            url = f"{self.BASE_URL}{self.SEARCH_ENDPOINT}"
            response = self.session.get(url, params=params)
            
            # Get rate limit info from headers
            diagnostics['rate_limit_info'] = {
                'remaining': response.headers.get('x-rate-limit-remaining'),
                'reset': response.headers.get('x-rate-limit-reset')
            }

            response.raise_for_status()
            response_data = response.json()
            
            diagnostics['api_accessible'] = True

            # Check response
            if 'data' in response_data:
                diagnostics['test_query_result'] = {
                    'tweets_found': len(response_data['data']),
                    'sample_tweet': response_data['data'][0] if response_data['data'] else None
                }
            elif 'errors' in response_data:
                diagnostics['error'] = response_data['errors']
            else:
                diagnostics['test_query_result'] = {
                    'tweets_found': 0,
                    'response_structure': list(response_data.keys()),
                    'full_response': response_data
                }

        except requests.exceptions.RequestException as e:
            diagnostics['error'] = str(e)
            if hasattr(e, 'response') and e.response:
                diagnostics['http_status'] = e.response.status_code
                try:
                    diagnostics['error_details'] = e.response.json()
                except:
                    diagnostics['error_details'] = e.response.text[:500]
            diagnostics['api_accessible'] = False
        except Exception as e:
            diagnostics['error'] = str(e)
            diagnostics['api_accessible'] = False

        return diagnostics
    
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
        
        logger.info(f"Collected {len(all_tweets)} unique tweets")
        return all_tweets
