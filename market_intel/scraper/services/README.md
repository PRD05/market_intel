# Services Module

This directory contains all service classes for the market intelligence application.

## Structure

```
services/
├── __init__.py              # Module exports
├── twitter_scraper.py        # Twitter API v2 scraper (requires Bearer Token)
├── twitter_scraper_twikit.py # Twikit scraper (no API key required)
├── data_processor.py         # Data cleaning and processing
├── analyzer.py               # Sentiment analysis and signal generation
└── visualizer.py             # Data visualization
```

## Usage

All services are exported through the `__init__.py` file:

```python
from scraper.services import (
    TwitterScraper,
    create_twitter_scraper,
    DataProcessor,
    TweetAnalyzer,
    MemoryEfficientVisualizer,
)
```

## Service Classes

### TwitterScraper
- **File**: `twitter_scraper.py`
- **Purpose**: Scrapes tweets using Twitter API v2
- **Requires**: `TWITTER_BEARER_TOKEN` environment variable
- **Access Level**: Standard (7 days) or Academic Research (full archive)

### TwitterScraperTwikit
- **File**: `twitter_scraper_twikit.py`
- **Purpose**: Scrapes tweets using Twikit library (no API key)
- **Requires**: `pip install twikit`
- **Benefits**: No API key needed, can access more historical data

### DataProcessor
- **File**: `data_processor.py`
- **Purpose**: Cleans, normalizes, and stores tweet data
- **Features**: Unicode normalization, deduplication, Parquet storage

### TweetAnalyzer
- **File**: `analyzer.py`
- **Purpose**: Analyzes tweets and generates trading signals
- **Features**: TF-IDF, sentiment analysis, signal aggregation

### MemoryEfficientVisualizer
- **File**: `visualizer.py`
- **Purpose**: Creates visualizations from analyzed data
- **Features**: Signal trends, sentiment distribution, engagement metrics

## Factory Function

`create_twitter_scraper()` automatically selects the appropriate scraper:
- If `use_twikit=True`: Uses Twikit (if installed)
- If `use_twikit=False`: Uses Twitter API
- If `use_twikit=None`: Auto-detects based on availability

