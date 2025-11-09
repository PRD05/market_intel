"""
Data processing module for cleaning, normalizing, and storing tweets.
Handles Unicode, deduplication, and Parquet storage.
"""
import logging
import re
import hashlib
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import unicodedata

logger = logging.getLogger(__name__)


class DataProcessor:
    """Process and store tweet data efficiently"""
    
    def __init__(self, output_dir: str = "data"):
        """
        Initialize data processor
        
        Args:
            output_dir: Directory to store processed data
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.seen_hashes = set()
    
    def clean_text(self, text: str) -> str:
        """
        Clean and normalize text content
        
        Args:
            text: Raw text to clean
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Normalize Unicode (handle Indian language characters)
        text = unicodedata.normalize('NFKC', text)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special control characters but keep emojis and Indian language chars
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        # Strip leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def normalize_timestamp(self, timestamp) -> datetime:
        """Normalize timestamp to datetime object"""
        if isinstance(timestamp, str):
            try:
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                return datetime.now()
        elif isinstance(timestamp, datetime):
            return timestamp
        else:
            return datetime.now()
    
    def process_tweets(self, tweets: List[Dict]) -> List[Dict]:
        """
        Process and clean a list of tweets
        
        Args:
            tweets: List of raw tweet dictionaries
            
        Returns:
            List of processed tweet dictionaries
        """
        processed = []
        
        for tweet in tweets:
            try:
                # Clean content
                cleaned_content = self.clean_text(tweet.get('content', ''))
                if not cleaned_content:
                    continue
                
                # Normalize timestamp
                normalized_timestamp = self.normalize_timestamp(tweet.get('timestamp'))
                
                # Recalculate hash after cleaning
                content_hash = hashlib.sha256(cleaned_content.encode('utf-8')).hexdigest()
                
                # Check for duplicates
                if content_hash in self.seen_hashes:
                    continue
                
                self.seen_hashes.add(content_hash)
                
                # Clean mentions and hashtags
                mentions = [self.clean_text(m) for m in tweet.get('mentions', []) if m]
                hashtags = [self.clean_text(h) for h in tweet.get('hashtags', []) if h]
                
                processed_tweet = {
                    'username': self.clean_text(tweet.get('username', 'unknown')),
                    'timestamp': normalized_timestamp,
                    'content': cleaned_content,
                    'likes': int(tweet.get('likes', 0)),
                    'retweets': int(tweet.get('retweets', 0)),
                    'replies': int(tweet.get('replies', 0)),
                    'mentions': mentions,
                    'hashtags': hashtags,
                    'tweet_id': tweet.get('tweet_id'),
                    'url': tweet.get('url'),
                    'content_hash': content_hash,
                }
                
                processed.append(processed_tweet)
                
            except Exception as e:
                logger.warning(f"Error processing tweet: {e}")
                continue
        
        logger.info(f"Processed {len(processed)} tweets from {len(tweets)} raw")
        return processed
    
    def deduplicate(self, tweets: List[Dict]) -> List[Dict]:
        """
        Remove duplicate tweets based on content hash
        
        Args:
            tweets: List of tweet dictionaries
            
        Returns:
            Deduplicated list
        """
        seen = set()
        unique = []
        
        for tweet in tweets:
            content_hash = tweet.get('content_hash')
            if content_hash and content_hash not in seen:
                seen.add(content_hash)
                unique.append(tweet)
        
        return unique
    
    def to_dataframe(self, tweets: List[Dict]) -> pd.DataFrame:
        """Convert list of tweets to pandas DataFrame"""
        if not tweets:
            return pd.DataFrame()
        
        df = pd.DataFrame(tweets)
        
        # Ensure timestamp is datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Convert lists to strings for Parquet compatibility
        for col in ['mentions', 'hashtags']:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: ','.join(x) if isinstance(x, list) else str(x))
        
        return df
    
    def save_to_parquet(self, tweets: List[Dict], filename: Optional[str] = None) -> str:
        """
        Save tweets to Parquet format
        
        Args:
            tweets: List of processed tweet dictionaries
            filename: Optional filename (defaults to timestamp-based name)
            
        Returns:
            Path to saved file
        """
        if not tweets:
            return ""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tweets_{timestamp}.parquet"
        
        filepath = self.output_dir / filename
        
        try:
            df = self.to_dataframe(tweets)
            
            # Save to Parquet with compression
            table = pa.Table.from_pandas(df)
            pq.write_table(
                table,
                filepath,
                compression='snappy',  # Good balance of speed and compression
                use_dictionary=True,  # Better compression for string columns
            )
            
            logger.info(f"Saved {len(tweets)} tweets to {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error saving to Parquet: {e}")
            raise
    
    def load_from_parquet(self, filepath: str) -> pd.DataFrame:
        """Load tweets from Parquet file"""
        try:
            table = pq.read_table(filepath)
            df = table.to_pandas()
            
            # Convert string lists back to lists
            for col in ['mentions', 'hashtags']:
                if col in df.columns:
                    df[col] = df[col].apply(lambda x: x.split(',') if isinstance(x, str) and x else [])
            
            return df
        except Exception as e:
            logger.error(f"Error loading from Parquet: {e}")
            raise

