"""
Twitter/X scraper using Selenium for collecting Indian stock market tweets.
Handles rate limiting, anti-bot measures, and concurrent processing.
"""
import time
import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import random

logger = logging.getLogger(__name__)


class TwitterScraper:
    """Selenium-based Twitter scraper for Indian stock market tweets"""
    
    HASHTAGS = ['#nifty50', '#sensex', '#intraday', '#banknifty']
    MIN_TWEETS = 2000
    TIME_WINDOW_HOURS = 24
    
    def __init__(self, headless: bool = True, max_workers: int = 3):
        """
        Initialize the scraper
        
        Args:
            headless: Run browser in headless mode
            max_workers: Number of concurrent browser instances
        """
        self.headless = headless
        self.max_workers = max_workers
        self.drivers = []
        
    def _create_driver(self) -> webdriver.Chrome:
        """Create a configured Chrome driver with anti-detection measures"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument('--headless')
        
        # Anti-detection measures
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Memory optimization (keep JavaScript enabled for Twitter)
        # chrome_options.add_argument('--disable-images')  # Commented out as it may break layout
        
        driver = webdriver.Chrome(options=chrome_options)
        
        # Execute script to hide webdriver property
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    
    def _search_twitter(self, driver: webdriver.Chrome, hashtag: str) -> List[Dict]:
        """
        Search Twitter for a specific hashtag and extract tweets
        
        Args:
            driver: Selenium WebDriver instance
            hashtag: Hashtag to search for
            
        Returns:
            List of tweet dictionaries
        """
        tweets = []
        try:
            # Navigate to Twitter search
            search_url = f"https://twitter.com/search?q={hashtag}&src=typed_query&f=live"
            driver.get(search_url)
            
            # Wait for page to load
            time.sleep(random.uniform(2, 4))
            
            # Scroll and collect tweets
            last_height = driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scrolls = 50  # Limit scrolling to prevent infinite loops
            
            while len(tweets) < 500 and scroll_attempts < max_scrolls:
                # Find tweet elements
                try:
                    tweet_elements = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
                    
                    for element in tweet_elements:
                        try:
                            tweet_data = self._extract_tweet_data(element, hashtag)
                            if tweet_data and self._is_recent_tweet(tweet_data['timestamp']):
                                tweets.append(tweet_data)
                        except Exception as e:
                            logger.warning(f"Error extracting tweet: {e}")
                            continue
                    
                    # Remove duplicates based on content hash
                    seen_hashes = set()
                    unique_tweets = []
                    for tweet in tweets:
                        if tweet['content_hash'] not in seen_hashes:
                            seen_hashes.add(tweet['content_hash'])
                            unique_tweets.append(tweet)
                    tweets = unique_tweets
                    
                except Exception as e:
                    logger.warning(f"Error finding tweets: {e}")
                
                # Scroll down
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(1, 2))
                
                # Check if we've reached the end
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    scroll_attempts += 1
                    if scroll_attempts > 3:
                        break
                else:
                    scroll_attempts = 0
                    last_height = new_height
                
                # Rate limiting
                time.sleep(random.uniform(0.5, 1.5))
            
        except Exception as e:
            logger.error(f"Error searching for {hashtag}: {e}")
        
        return tweets
    
    def _extract_tweet_data(self, element, hashtag: str) -> Optional[Dict]:
        """Extract data from a tweet element"""
        try:
            # Extract username
            try:
                username_elem = element.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"] a')
                username = username_elem.get_attribute('href').split('/')[-1]
            except:
                username = "unknown"
            
            # Extract content
            try:
                content_elem = element.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]')
                content = content_elem.text
            except:
                try:
                    content_elem = element.find_element(By.CSS_SELECTOR, 'div[lang]')
                    content = content_elem.text
                except:
                    content = ""
            
            if not content:
                return None
            
            # Extract timestamp
            try:
                time_elem = element.find_element(By.CSS_SELECTOR, 'time')
                timestamp_str = time_elem.get_attribute('datetime')
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = datetime.now()
            except:
                timestamp = datetime.now()
            
            # Extract engagement metrics
            likes = self._extract_metric(element, 'like')
            retweets = self._extract_metric(element, 'retweet')
            replies = self._extract_metric(element, 'reply')
            
            # Extract mentions and hashtags
            mentions = re.findall(r'@(\w+)', content)
            hashtags = re.findall(r'#(\w+)', content, re.IGNORECASE)
            if hashtag.replace('#', '').lower() not in [h.lower() for h in hashtags]:
                hashtags.append(hashtag.replace('#', ''))
            
            # Extract tweet ID from URL
            try:
                link_elem = element.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                tweet_url = link_elem.get_attribute('href')
                tweet_id = tweet_url.split('/status/')[-1].split('?')[0] if '/status/' in tweet_url else None
            except:
                tweet_url = None
                tweet_id = None
            
            # Create content hash for deduplication
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            
            return {
                'username': username,
                'timestamp': timestamp,
                'content': content,
                'likes': likes,
                'retweets': retweets,
                'replies': replies,
                'mentions': mentions,
                'hashtags': hashtags,
                'tweet_id': tweet_id,
                'url': tweet_url,
                'content_hash': content_hash,
            }
            
        except Exception as e:
            logger.warning(f"Error extracting tweet data: {e}")
            return None
    
    def _extract_metric(self, element, metric_type: str) -> int:
        """Extract engagement metric (likes, retweets, replies)"""
        try:
            selectors = {
                'like': '[data-testid="like"]',
                'retweet': '[data-testid="retweet"]',
                'reply': '[data-testid="reply"]',
            }
            
            metric_elem = element.find_element(By.CSS_SELECTOR, selectors.get(metric_type, ''))
            metric_text = metric_elem.text.strip()
            
            # Parse numbers (handle K, M suffixes)
            if 'K' in metric_text:
                return int(float(metric_text.replace('K', '')) * 1000)
            elif 'M' in metric_text:
                return int(float(metric_text.replace('M', '')) * 1000000)
            else:
                return int(metric_text) if metric_text.isdigit() else 0
        except:
            return 0
    
    def _is_recent_tweet(self, timestamp: datetime) -> bool:
        """Check if tweet is within the last 24 hours"""
        cutoff = datetime.now() - timedelta(hours=self.TIME_WINDOW_HOURS)
        return timestamp >= cutoff
    
    def scrape_hashtag(self, hashtag: str) -> List[Dict]:
        """Scrape tweets for a single hashtag"""
        driver = None
        try:
            driver = self._create_driver()
            tweets = self._search_twitter(driver, hashtag)
            logger.info(f"Scraped {len(tweets)} tweets for {hashtag}")
            return tweets
        except Exception as e:
            logger.error(f"Error scraping {hashtag}: {e}")
            return []
        finally:
            if driver:
                driver.quit()
    
    def scrape_all_hashtags(self) -> List[Dict]:
        """
        Scrape all hashtags concurrently
        
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

