"""
Analysis module for converting tweets to trading signals.
Implements TF-IDF, sentiment analysis, and signal aggregation.
"""
import logging
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from collections import Counter
from scipy import stats
import re

logger = logging.getLogger(__name__)


class TweetAnalyzer:
    """Analyze tweets and convert to trading signals"""
    
    # Market-related keywords for feature engineering
    BULLISH_KEYWORDS = ['buy', 'bull', 'bullish', 'up', 'rise', 'gain', 'profit', 'long', 
                        'rally', 'surge', 'breakout', 'support', 'strong', 'positive']
    BEARISH_KEYWORDS = ['sell', 'bear', 'bearish', 'down', 'fall', 'loss', 'short', 
                        'crash', 'drop', 'breakdown', 'resistance', 'weak', 'negative']
    
    def __init__(self, max_features: int = 1000, n_components: int = 50):
        """
        Initialize analyzer
        
        Args:
            max_features: Maximum features for TF-IDF
            n_components: Number of components for dimensionality reduction
        """
        self.max_features = max_features
        self.n_components = n_components
        self.vectorizer = None
        self.svd = None
        self.is_fitted = False
    
    def fit(self, texts: List[str]):
        """
        Fit TF-IDF vectorizer and SVD on training texts
        
        Args:
            texts: List of tweet texts
        """
        try:
            # Fit TF-IDF
            self.vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.95,
            )
            
            tfidf_matrix = self.vectorizer.fit_transform(texts)
            
            # Dimensionality reduction for memory efficiency
            self.svd = TruncatedSVD(n_components=self.n_components, random_state=42)
            self.svd.fit(tfidf_matrix)
            
            self.is_fitted = True
        except Exception as e:
            logger.error(f"Error fitting analyzer: {e}")
            raise
    
    def extract_tfidf_features(self, text: str) -> Dict:
        """
        Extract TF-IDF features from text
        
        Args:
            text: Tweet text
            
        Returns:
            Dictionary of TF-IDF features
        """
        if not self.is_fitted:
            raise ValueError("Analyzer must be fitted before extracting features")
        
        try:
            # Transform text to TF-IDF
            tfidf_vector = self.vectorizer.transform([text])
            
            # Apply dimensionality reduction
            reduced_vector = self.svd.transform(tfidf_vector)
            
            # Convert to dictionary
            features = {
                f'tfidf_{i}': float(reduced_vector[0][i])
                for i in range(self.n_components)
            }
            
            return features
            
        except Exception as e:
            logger.warning(f"Error extracting TF-IDF features: {e}")
            return {}
    
    def calculate_sentiment_score(self, text: str) -> Tuple[float, str]:
        """
        Calculate sentiment score using keyword-based approach
        
        Args:
            text: Tweet text
            
        Returns:
            Tuple of (score, label) where score is -1 to 1, label is 'positive', 'negative', or 'neutral'
        """
        text_lower = text.lower()
        
        bullish_count = sum(1 for keyword in self.BULLISH_KEYWORDS if keyword in text_lower)
        bearish_count = sum(1 for keyword in self.BEARISH_KEYWORDS if keyword in text_lower)
        
        # Calculate score
        total = bullish_count + bearish_count
        if total == 0:
            return 0.0, 'neutral'
        
        score = (bullish_count - bearish_count) / total
        
        # Normalize to -1 to 1 range
        score = max(-1.0, min(1.0, score))
        
        # Determine label
        if score > 0.2:
            label = 'positive'
        elif score < -0.2:
            label = 'negative'
        else:
            label = 'neutral'
        
        return score, label
    
    def calculate_engagement_score(self, likes: int, retweets: int, replies: int) -> float:
        """
        Calculate normalized engagement score
        
        Args:
            likes: Number of likes
            retweets: Number of retweets
            replies: Number of replies
            
        Returns:
            Normalized engagement score (0 to 1)
        """
        # Weighted engagement: likes (1x), retweets (2x), replies (1.5x)
        weighted_engagement = likes + (retweets * 2) + (replies * 1.5)
        
        # Normalize using log scale to handle outliers
        if weighted_engagement == 0:
            return 0.0
        
        # Log normalization (max expected ~100K engagement)
        normalized = np.log1p(weighted_engagement) / np.log1p(100000)
        
        return min(1.0, normalized)
    
    def extract_custom_features(self, text: str, mentions: List[str], hashtags: List[str]) -> Dict:
        """
        Extract custom features for trading signals
        
        Args:
            text: Tweet text
            mentions: List of mentions
            hashtags: List of hashtags
            
        Returns:
            Dictionary of custom features
        """
        features = {}
        
        # Text length features
        features['text_length'] = len(text)
        features['word_count'] = len(text.split())
        
        # Hashtag features
        features['hashtag_count'] = len(hashtags)
        features['has_market_hashtag'] = 1 if any(
            h.lower() in ['nifty50', 'sensex', 'intraday', 'banknifty'] 
            for h in hashtags
        ) else 0
        
        # Mention features
        features['mention_count'] = len(mentions)
        
        # Number features (potential price mentions)
        numbers = re.findall(r'\d+\.?\d*', text)
        features['number_count'] = len(numbers)
        features['has_large_number'] = 1 if any(
            float(n) > 1000 for n in numbers if n.replace('.', '').isdigit()
        ) else 0
        
        # Question/exclamation features (indicates uncertainty/emphasis)
        features['question_count'] = text.count('?')
        features['exclamation_count'] = text.count('!')
        
        return features
    
    def calculate_composite_signal(
        self, 
        sentiment_score: float,
        engagement_score: float,
        custom_features: Dict
    ) -> float:
        """
        Calculate composite trading signal
        
        Args:
            sentiment_score: Sentiment score (-1 to 1)
            engagement_score: Engagement score (0 to 1)
            custom_features: Dictionary of custom features
            
        Returns:
            Composite signal value
        """
        # Weighted combination
        sentiment_weight = 0.5
        engagement_weight = 0.3
        custom_weight = 0.2
        
        # Custom feature contribution
        custom_contribution = (
            custom_features.get('has_market_hashtag', 0) * 0.1 +
            min(custom_features.get('mention_count', 0) / 5, 1.0) * 0.1
        )
        
        # Composite signal
        composite = (
            sentiment_score * sentiment_weight +
            engagement_score * engagement_weight +
            custom_contribution * custom_weight
        )
        
        return composite
    
    def calculate_confidence_interval(
        self,
        signals: List[float],
        confidence_level: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculate confidence interval for signals
        
        Args:
            signals: List of signal values
            confidence_level: Confidence level (default 0.95)
            
        Returns:
            Tuple of (lower_bound, upper_bound)
        """
        if not signals:
            return 0.0, 0.0
        
        signals_array = np.array(signals)
        mean = np.mean(signals_array)
        std = np.std(signals_array)
        
        # Z-score for confidence level
        z_score = stats.norm.ppf((1 + confidence_level) / 2)
        
        margin = z_score * std / np.sqrt(len(signals))
        
        return mean - margin, mean + margin
    
    def analyze_tweet(self, tweet: Dict) -> Dict:
        """
        Analyze a single tweet and generate signal
        
        Args:
            tweet: Tweet dictionary
            
        Returns:
            Dictionary with analysis results
        """
        text = tweet.get('content', '')
        
        # Extract features
        tfidf_features = self.extract_tfidf_features(text) if self.is_fitted else {}
        sentiment_score, sentiment_label = self.calculate_sentiment_score(text)
        engagement_score = self.calculate_engagement_score(
            tweet.get('likes', 0),
            tweet.get('retweets', 0),
            tweet.get('replies', 0)
        )
        custom_features = self.extract_custom_features(
            text,
            tweet.get('mentions', []),
            tweet.get('hashtags', [])
        )
        
        # Calculate composite signal
        composite_signal = self.calculate_composite_signal(
            sentiment_score,
            engagement_score,
            custom_features
        )
        
        return {
            'tfidf_vector': tfidf_features,
            'sentiment_score': sentiment_score,
            'sentiment_label': sentiment_label,
            'engagement_score': engagement_score,
            'custom_features': custom_features,
            'composite_signal': composite_signal,
        }
    
    def analyze_batch(self, tweets: List[Dict]) -> List[Dict]:
        """
        Analyze a batch of tweets
        
        Args:
            tweets: List of tweet dictionaries
            
        Returns:
            List of analysis results
        """
        results = []
        
        for tweet in tweets:
            try:
                analysis = self.analyze_tweet(tweet)
                results.append(analysis)
            except Exception as e:
                logger.warning(f"Error analyzing tweet: {e}")
                continue
        
        return results
    
    def aggregate_signals(self, analyses: List[Dict]) -> Dict:
        """
        Aggregate signals from multiple analyses
        
        Args:
            analyses: List of analysis dictionaries
            
        Returns:
            Aggregated signal dictionary
        """
        if not analyses:
            return {}
        
        signals = [a.get('composite_signal', 0) for a in analyses]
        sentiment_scores = [a.get('sentiment_score', 0) for a in analyses]
        engagement_scores = [a.get('engagement_score', 0) for a in analyses]
        
        # Calculate statistics
        mean_signal = np.mean(signals)
        std_signal = np.std(signals)
        
        lower_bound, upper_bound = self.calculate_confidence_interval(signals)
        
        # Sentiment distribution
        sentiment_labels = [a.get('sentiment_label', 'neutral') for a in analyses]
        sentiment_dist = Counter(sentiment_labels)
        
        return {
            'mean_signal': float(mean_signal),
            'std_signal': float(std_signal),
            'confidence_interval_lower': float(lower_bound),
            'confidence_interval_upper': float(upper_bound),
            'mean_sentiment': float(np.mean(sentiment_scores)),
            'mean_engagement': float(np.mean(engagement_scores)),
            'total_tweets': len(analyses),
            'sentiment_distribution': dict(sentiment_dist),
        }

