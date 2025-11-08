"""
Twitter/X API v2 scraper using OAuth 2.0 Bearer Token for collecting Indian stock market tweets.
Uses official Twitter API with Academic Research access for comprehensive tweet search.
"""
import time
import hashlib
import logging
import re
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class TwitterScraper:
    """Twitter API v2 scraper using OAuth 2.0 Bearer Token"""
    
    HASHTAGS = ['#nifty50', '#sensex', '#intraday', '#banknifty']
    MIN_TWEETS = 2000
    # Note: Standard API access allows 7 days (168 hours) max
    # Academic Research access allows full archive
    # Set to 168 for standard access, 240+ for Academic Research
    TIME_WINDOW_HOURS = int(os.environ.get('TWITTER_TIME_WINDOW_HOURS', '168'))  # Default to 7 days for standard access

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
            
            # Warn about time window vs API access level
            if self.TIME_WINDOW_HOURS > 168:
                logger.warning(f"TIME_WINDOW_HOURS is {self.TIME_WINDOW_HOURS} hours ({self.TIME_WINDOW_HOURS/24:.1f} days)")
                logger.warning("Standard API access only allows 7 days (168 hours) of tweet history")
                logger.warning("For longer time windows, you need Academic Research access")
                logger.warning("Apply at: https://developer.twitter.com/en/portal/petition/academic-research")
                logger.warning("Or set TWITTER_TIME_WINDOW_HOURS=168 for standard access")
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
            logger.error("=" * 60)
            logger.error("❌ Twitter Bearer Token not configured!")
            logger.error("   This scraper requires TWITTER_BEARER_TOKEN environment variable")
            logger.error("   Options:")
            logger.error("   1. Set TWITTER_BEARER_TOKEN environment variable")
            logger.error("   2. Use Twikit scraper instead: pip install twikit")
            logger.error("      Then use: curl -X POST ... -d '{\"use_twikit\": true}'")
            logger.error("=" * 60)
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
                status_code = e.response.status_code
                logger.error(f"HTTP Status Code: {status_code}")
                
                # Try to get error details from response
                try:
                    error_data = e.response.json()
                    logger.error(f"Error response: {json.dumps(error_data, indent=2)}")
                    
                    if 'errors' in error_data:
                        for error in error_data['errors']:
                            logger.error(f"API Error: {error.get('message')} (Code: {error.get('code')})")
                except:
                    logger.error(f"Response text: {e.response.text[:500]}")
                
                if status_code == 429:
                    logger.warning("Rate limit exceeded. Waiting before retry...")
                    time.sleep(60)  # Wait 1 minute on rate limit
                elif status_code == 401:
                    logger.error("Authentication failed. Check your Bearer Token.")
                    logger.error("Verify your Bearer Token is correct and not expired.")
                elif status_code == 403:
                    logger.error("Access forbidden. You may need Academic Research access.")
                    logger.error("Standard API access only allows 7 days of tweet history.")
                    logger.error("Apply for Academic Research access at:")
                    logger.error("https://developer.twitter.com/en/portal/petition/academic-research")
                elif status_code == 400:
                    logger.error("Bad request. Check your query parameters.")
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

                # Log full response for debugging
                logger.debug(f"API Response for '{query}': {json.dumps(response, indent=2)}")

                # Check for errors in response
                if 'errors' in response:
                    for error in response['errors']:
                        logger.error(f"Twitter API error: {error.get('message', 'Unknown error')} (Code: {error.get('code', 'N/A')})")
                        if error.get('code') == 25:  # Query too complex
                            logger.warning("Query might be too complex. Try simplifying the search query.")
                        elif error.get('code') == 32:  # Could not authenticate
                            logger.error("Authentication failed. Check your Bearer Token.")
                        elif error.get('code') == 88:  # Rate limit exceeded
                            logger.warning("Rate limit exceeded. Will retry after waiting.")

                # Check for warnings
                if 'warnings' in response:
                    for warning in response['warnings']:
                        logger.warning(f"Twitter API warning: {warning}")

                # Process tweets
                if 'data' in response and response['data']:
                    logger.info(f"API returned {len(response['data'])} tweets in response")
                    for tweet in response['data']:
                        tweet_data = self._process_tweet_data(tweet, response.get('includes', {}))
                        if tweet_data:
                            tweets.append(tweet_data)
                elif 'data' not in response:
                    logger.warning(f"No 'data' field in API response. Full response: {response}")
                else:
                    logger.info(f"API returned empty data array for query: {query}")

                # Check result count in meta
                meta = response.get('meta', {})
                result_count = meta.get('result_count', 0)
                logger.info(f"API meta shows result_count: {result_count}")

                # Check for next page
                if 'next_token' not in meta:
                    logger.debug("No next_token found, reached end of results")
                    break
                next_token = meta['next_token']

                # Avoid infinite loops
                if len(tweets) >= max_results:
                    break

            except Exception as e:
                logger.error(f"Error searching tweets for query '{query}': {e}", exc_info=True)
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

        # Build search query - try multiple query formats
        queries = [
            f"{hashtag} lang:en",  # English tweets only
            f"{hashtag}",  # All languages
            f'"{hashtag}"',  # Exact phrase match
        ]

        all_tweets = []
        for query in queries:
            logger.info(f"Trying query: {query}")
            tweets = self._search_tweets(query, max_results=500)
            
            if tweets:
                logger.info(f"Found {len(tweets)} tweets with query: {query}")
                all_tweets.extend(tweets)
                break  # Use first successful query
            else:
                logger.debug(f"No tweets found with query: {query}")

        # Filter for recent tweets
        recent_tweets = []
        for tweet in all_tweets:
            if self._is_recent_tweet(tweet['timestamp']):
                recent_tweets.append(tweet)
            else:
                logger.debug(f"Tweet filtered out (too old): {tweet['timestamp']}")

        logger.info(f"Collected {len(recent_tweets)} recent tweets for {hashtag} (out of {len(all_tweets)} total)")
        return recent_tweets
    
    def _is_recent_tweet(self, timestamp: datetime) -> bool:
        """Check if tweet is within the configured time window"""
        cutoff = datetime.now() - timedelta(hours=self.TIME_WINDOW_HOURS)
        is_recent = timestamp >= cutoff
        if not is_recent:
            logger.debug(f"Tweet from {timestamp} is older than {self.TIME_WINDOW_HOURS} hours (cutoff: {cutoff})")
        return is_recent

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
        Scrape all hashtags concurrently using Twitter API
        
        Returns:
            List of all unique tweets
        """
        all_tweets = []
        seen_hashes = set()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_hashtag = {
                executor.submit(self.scrape_hashtag, hashtag): hashtag
                for hashtag in self.HASHTAGS
            }
            
            for future in as_completed(future_to_hashtag):
                hashtag = future_to_hashtag[future]
                try:
                    tweets = future.result()
                    for tweet in tweets:
                        if tweet['content_hash'] not in seen_hashes:
                            seen_hashes.add(tweet['content_hash'])
                            all_tweets.append(tweet)
                except Exception as e:
                    logger.error(f"Error processing {hashtag}: {e}")
        
        logger.info(f"Total unique tweets collected: {len(all_tweets)}")
        return all_tweets
