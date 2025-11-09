"""
Memory-efficient visualization module for large datasets.
Uses streaming plots and data sampling techniques.
"""
import logging
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from typing import List, Dict, Optional
from pathlib import Path
import seaborn as sns

logger = logging.getLogger(__name__)


class MemoryEfficientVisualizer:
    """Create memory-efficient visualizations for large datasets"""
    
    def __init__(self, output_dir: str = "visualizations", max_points: int = 10000):
        """
        Initialize visualizer
        
        Args:
            output_dir: Directory to save visualizations
            max_points: Maximum points to plot (for sampling)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.max_points = max_points
        sns.set_style("whitegrid")
    
    def sample_data(self, data: pd.DataFrame, max_points: int = None) -> pd.DataFrame:
        """
        Sample data for visualization to reduce memory usage
        
        Args:
            data: DataFrame to sample
            max_points: Maximum number of points (defaults to self.max_points)
            
        Returns:
            Sampled DataFrame
        """
        if max_points is None:
            max_points = self.max_points
        
        if len(data) <= max_points:
            return data
        
        # Stratified sampling to preserve distribution
        if 'timestamp' in data.columns:
            # Time-based sampling
            data = data.sort_values('timestamp')
            step = len(data) // max_points
            sampled = data.iloc[::step].copy()
        else:
            # Random sampling
            sampled = data.sample(n=max_points, random_state=42)
        
        return sampled
    
    def plot_signal_over_time(
        self,
        df: pd.DataFrame,
        signal_column: str = 'composite_signal',
        time_column: str = 'timestamp',
        filename: Optional[str] = None
    ) -> str:
        """
        Create streaming plot of signals over time
        
        Args:
            df: DataFrame with signals
            signal_column: Column name for signal values
            time_column: Column name for timestamps
            filename: Optional filename
            
        Returns:
            Path to saved plot
        """
        if filename is None:
            filename = "signal_over_time.png"
        
        filepath = self.output_dir / filename
        
        try:
            # Sample data if needed
            sampled_df = self.sample_data(df)
            
            # Ensure timestamp is datetime
            if time_column in sampled_df.columns:
                sampled_df[time_column] = pd.to_datetime(sampled_df[time_column])
                sampled_df = sampled_df.sort_values(time_column)
            
            # Create figure with memory-efficient settings
            fig, ax = plt.subplots(figsize=(12, 6))
            
            # Plot with reduced alpha for large datasets
            alpha = 0.3 if len(sampled_df) > 1000 else 0.7
            
            ax.scatter(
                sampled_df[time_column],
                sampled_df[signal_column],
                alpha=alpha,
                s=10,
                c=sampled_df[signal_column],
                cmap='RdYlGn',
                edgecolors='none'
            )
            
            # Add rolling average line
            if len(sampled_df) > 100:
                window = min(100, len(sampled_df) // 10)
                rolling_mean = sampled_df[signal_column].rolling(window=window).mean()
                ax.plot(sampled_df[time_column], rolling_mean, 'b-', linewidth=2, label='Rolling Mean')
            
            ax.set_xlabel('Time')
            ax.set_ylabel('Composite Signal')
            ax.set_title('Trading Signals Over Time')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()
            return str(filepath)
        except Exception as e:
            logger.error(f"Error creating signal plot: {e}")
            plt.close()
            raise
    
    def plot_sentiment_distribution(
        self,
        df: pd.DataFrame,
        sentiment_column: str = 'sentiment_label',
        filename: Optional[str] = None
    ) -> str:
        """
        Plot sentiment distribution
        
        Args:
            df: DataFrame with sentiment data
            sentiment_column: Column name for sentiment labels
            filename: Optional filename
            
        Returns:
            Path to saved plot
        """
        if filename is None:
            filename = "sentiment_distribution.png"
        
        filepath = self.output_dir / filename
        
        try:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
            
            # Count plot
            sentiment_counts = df[sentiment_column].value_counts()
            ax1.bar(sentiment_counts.index, sentiment_counts.values, color=['green', 'red', 'gray'])
            ax1.set_xlabel('Sentiment')
            ax1.set_ylabel('Count')
            ax1.set_title('Sentiment Distribution (Count)')
            ax1.grid(True, alpha=0.3, axis='y')
            
            # Pie chart
            ax2.pie(
                sentiment_counts.values,
                labels=sentiment_counts.index,
                autopct='%1.1f%%',
                colors=['green', 'red', 'gray'],
                startangle=90
            )
            ax2.set_title('Sentiment Distribution (Percentage)')
            
            plt.tight_layout()
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()
            return str(filepath)
        except Exception as e:
            logger.error(f"Error creating sentiment plot: {e}")
            plt.close()
            raise
    
    def plot_engagement_vs_sentiment(
        self,
        df: pd.DataFrame,
        engagement_column: str = 'engagement_score',
        sentiment_column: str = 'sentiment_score',
        filename: Optional[str] = None
    ) -> str:
        """
        Plot engagement vs sentiment scatter plot
        
        Args:
            df: DataFrame with engagement and sentiment data
            engagement_column: Column name for engagement scores
            sentiment_column: Column name for sentiment scores
            filename: Optional filename
            
        Returns:
            Path to saved plot
        """
        if filename is None:
            filename = "engagement_vs_sentiment.png"
        
        filepath = self.output_dir / filename
        
        try:
            # Sample data
            sampled_df = self.sample_data(df)
            
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Create scatter plot with color coding
            scatter = ax.scatter(
                sampled_df[sentiment_column],
                sampled_df[engagement_column],
                alpha=0.5,
                s=20,
                c=sampled_df[sentiment_column],
                cmap='RdYlGn',
                edgecolors='none'
            )
            
            ax.set_xlabel('Sentiment Score')
            ax.set_ylabel('Engagement Score')
            ax.set_title('Engagement vs Sentiment')
            ax.grid(True, alpha=0.3)
            plt.colorbar(scatter, ax=ax, label='Sentiment')
            
            plt.tight_layout()
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()
            return str(filepath)
        except Exception as e:
            logger.error(f"Error creating engagement plot: {e}")
            plt.close()
            raise
    
    def plot_signal_aggregation(
        self,
        aggregated_signals: Dict,
        filename: Optional[str] = None
    ) -> str:
        """
        Plot aggregated signal statistics with confidence intervals
        
        Args:
            aggregated_signals: Dictionary with aggregated signal data
            filename: Optional filename
            
        Returns:
            Path to saved plot
        """
        if filename is None:
            filename = "signal_aggregation.png"
        
        filepath = self.output_dir / filename
        
        try:
            fig, axes = plt.subplots(2, 2, figsize=(14, 10))
            
            # Signal distribution
            mean_signal = aggregated_signals.get('mean_signal', 0)
            std_signal = aggregated_signals.get('std_signal', 0)
            lower = aggregated_signals.get('confidence_interval_lower', 0)
            upper = aggregated_signals.get('confidence_interval_upper', 0)
            
            # Plot 1: Signal with confidence interval
            ax1 = axes[0, 0]
            ax1.barh(['Mean Signal'], [mean_signal], color='blue', alpha=0.7)
            ax1.errorbar([mean_signal], [0], xerr=[[mean_signal - lower], [upper - mean_signal]], 
                        fmt='o', color='red', capsize=10, label='95% CI')
            ax1.axvline(0, color='black', linestyle='--', alpha=0.5)
            ax1.set_xlabel('Signal Value')
            ax1.set_title('Aggregated Signal with Confidence Interval')
            ax1.legend()
            ax1.grid(True, alpha=0.3, axis='x')
            
            # Plot 2: Sentiment distribution
            ax2 = axes[0, 1]
            sentiment_dist = aggregated_signals.get('sentiment_distribution', {})
            if sentiment_dist:
                ax2.bar(sentiment_dist.keys(), sentiment_dist.values(), 
                       color=['green', 'red', 'gray'], alpha=0.7)
                ax2.set_xlabel('Sentiment')
                ax2.set_ylabel('Count')
                ax2.set_title('Sentiment Distribution')
                ax2.grid(True, alpha=0.3, axis='y')
            
            # Plot 3: Statistics
            ax3 = axes[1, 0]
            stats = {
                'Mean Signal': mean_signal,
                'Mean Sentiment': aggregated_signals.get('mean_sentiment', 0),
                'Mean Engagement': aggregated_signals.get('mean_engagement', 0),
            }
            ax3.barh(list(stats.keys()), list(stats.values()), color='steelblue', alpha=0.7)
            ax3.set_xlabel('Value')
            ax3.set_title('Aggregated Statistics')
            ax3.grid(True, alpha=0.3, axis='x')
            
            # Plot 4: Total tweets
            ax4 = axes[1, 1]
            total_tweets = aggregated_signals.get('total_tweets', 0)
            ax4.text(0.5, 0.5, f'Total Tweets\n{total_tweets}', 
                    ha='center', va='center', fontsize=20, fontweight='bold')
            ax4.set_xlim(0, 1)
            ax4.set_ylim(0, 1)
            ax4.axis('off')
            ax4.set_title('Dataset Size')
            
            plt.tight_layout()
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()
            return str(filepath)
        except Exception as e:
            logger.error(f"Error creating aggregation plot: {e}")
            plt.close()
            raise

