# Setup Guide

## Prerequisites

1. **Python 3.8+**
   ```bash
   python --version
   ```

2. **Chrome Browser**
   - Install Google Chrome from https://www.google.com/chrome/
   - The scraper uses Selenium which requires Chrome

3. **ChromeDriver**
   - ChromeDriver is automatically managed by Selenium 4.6+
   - If you encounter issues, you can manually install:
     ```bash
     # Using webdriver-manager (included in requirements)
     # Or download from https://chromedriver.chromium.org/
     ```

## Installation Steps

### 1. Clone or navigate to the project directory
```bash
cd qode_invest_project
```

### 2. Create virtual environment
```bash
python -m venv venv
```

### 3. Activate virtual environment
```bash
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Navigate to Django project
```bash
cd market_intel
```

### 6. Run migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 7. Create superuser (optional)
```bash
python manage.py createsuperuser
```

### 8. Run the server
```bash
python manage.py runserver
```

## Usage

### Option 1: Using API Endpoints

1. **Start the server**
   ```bash
   python manage.py runserver
   ```

2. **Scrape tweets** (in another terminal or using curl/Postman)
   ```bash
   curl -X POST http://localhost:8000/api/scrape/
   ```

3. **Analyze tweets**
   ```bash
   curl -X POST http://localhost:8000/api/analyze/
   ```

4. **Generate visualizations**
   ```bash
   curl -X POST http://localhost:8000/api/visualize/
   ```

5. **Get statistics**
   ```bash
   curl http://localhost:8000/api/stats/
   ```

### Option 2: Using Management Commands

1. **Scrape tweets**
   ```bash
   python manage.py scrape_tweets --headless --workers 3
   ```

2. **Analyze tweets**
   ```bash
   python manage.py analyze_tweets
   ```

## Troubleshooting

### ChromeDriver Issues

If you encounter ChromeDriver errors:

1. **Check Chrome version**
   ```bash
   google-chrome --version  # Linux
   # Or check in Chrome: chrome://version
   ```

2. **Install webdriver-manager** (already in requirements)
   ```bash
   pip install webdriver-manager
   ```

3. **Update the scraper** to use webdriver-manager (optional):
   ```python
   from selenium.webdriver.chrome.service import Service
   from webdriver_manager.chrome import ChromeDriverManager
   
   service = Service(ChromeDriverManager().install())
   driver = webdriver.Chrome(service=service, options=chrome_options)
   ```

### Twitter Access Issues

- Twitter may require login for some searches
- The scraper uses public search URLs, but Twitter's UI may change
- If scraping fails, check:
  - Internet connection
  - Twitter's current UI structure
  - Rate limiting (wait and retry)

### Memory Issues

For large datasets:
- Reduce `max_workers` in scraper
- Increase system memory
- Use data sampling (already implemented in visualizer)

## Notes

- The scraper runs in headless mode by default (no browser window)
- Scraping may take 30-60 minutes for 2000+ tweets
- Data is saved to both SQLite database and Parquet files
- Visualizations are saved to `visualizations/` directory
- Logs are written to `scraper.log`

