# Quick Start Guide

## Fast Setup (5 minutes)

```bash
# 1. Navigate to project
cd market_intel

# 2. Activate virtual environment (if not already)
source ../venv/bin/activate  # or: venv\Scripts\activate on Windows

# 3. Install dependencies (if not done)
pip install -r ../requirements.txt

# 4. Run migrations
python manage.py migrate

# 5. Start server
python manage.py runserver
```

## Quick Test

### Using API (Recommended)

1. **Scrape tweets** (takes 30-60 minutes)
   ```bash
   curl -X POST http://localhost:8000/api/scrape/
   ```
   Returns: `{"status": "started", "session_id": 1, ...}`

2. **Check progress** (in Django admin or check database)
   - Visit: http://localhost:8000/admin/scraper/scrapingsession/

3. **Analyze tweets** (after scraping completes)
   ```bash
   curl -X POST http://localhost:8000/api/analyze/
   ```

4. **Generate visualizations**
   ```bash
   curl -X POST http://localhost:8000/api/visualize/
   ```

5. **View statistics**
   ```bash
   curl http://localhost:8000/api/stats/
   ```

### Using Management Commands

```bash
# Scrape tweets
python manage.py scrape_tweets --headless

# Analyze tweets
python manage.py analyze_tweets
```

## Expected Output

After running the full pipeline:

1. **Database**: Tweets and signals stored in SQLite (`db.sqlite3`)
2. **Parquet files**: In `data/` directory (efficient storage)
3. **Visualizations**: In `visualizations/` directory:
   - `signal_over_time.png`
   - `sentiment_distribution.png`
   - `engagement_vs_sentiment.png`
   - `signal_aggregation.png`
4. **Logs**: `scraper.log` file

## Troubleshooting

**ChromeDriver error?**
- Make sure Chrome is installed
- Selenium 4.6+ auto-manages ChromeDriver

**No tweets collected?**
- Twitter UI may have changed
- Check internet connection
- Try running without `--headless` to see what's happening

**Memory issues?**
- Reduce workers: `--workers 1`
- Close other applications

## Next Steps

- Read full [README.md](README.md) for detailed documentation
- Check [SETUP.md](SETUP.md) for detailed setup instructions
- Explore Django admin at http://localhost:8000/admin/

