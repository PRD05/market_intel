# Twitter/X Login Guide

This guide explains how to configure authentication for scraping tweets from Twitter/X.

## Prerequisites

Make sure you have:
- A valid Twitter/X account
- Chrome browser installed
- Environment variables configured in `.env` file

## Setup Instructions

### Step 1: Copy Environment Template

```bash
cd market_intel
cp .env.example .env
```

### Step 2: Configure Authentication

Edit the `.env` file and add your credentials:

```bash
# Required: Your Twitter credentials
TWITTER_USERNAME=your_username
TWITTER_PASSWORD=your_password
TWITTER_EMAIL=your_email@example.com

# Optional: Enable debug mode to see the browser
TWITTER_DEBUG_MODE=False
```

### Step 3: Run the Server

```bash
python manage.py runserver
```

### Step 4: Start Scraping

```bash
curl -X POST http://127.0.0.1:8000/api/scrape/
```

## How It Works

1. **Selenium Login**: The scraper uses Selenium to automate login to Twitter/X
2. **Cookie Extraction**: After successful login, it extracts authentication cookies
3. **Twikit Scraping**: Uses the extracted cookies with Twikit for efficient scraping
4. **Tweet Collection**: Scrapes tweets for configured hashtags (#nifty50, #sensex, #intraday, #banknifty)

## Authentication Flow

```
Start → Load credentials from .env
  ↓
  ├─ If CT0 + AUTH_TOKEN exist → Use cookie-based auth (fast)
  │    ↓
  │    → Transfer cookies to Twikit → Start scraping
  │
  └─ If USERNAME + PASSWORD exist → Use Selenium login
       ↓
       → Open browser → Login → Extract cookies → Transfer to Twikit → Start scraping
```

## Features

### Human-Like Behavior
- Types credentials slowly (100-150ms between keystrokes)
- Adds realistic delays between actions
- Navigates like a human user
- Uses stealth settings to avoid detection

### Anti-Detection Measures
- Hides webdriver properties
- Uses realistic user agent
- Disables automation flags
- New headless mode

### Error Handling
- Detects password reset redirects
- Handles phone/email verification screens
- Checks for CAPTCHA challenges
- Provides detailed error messages

## Debug Mode

To see the browser window during login (helpful for troubleshooting):

```bash
# In .env file
TWITTER_DEBUG_MODE=True
```

This will show the Chrome browser window so you can see what's happening during login.

## Troubleshooting

### Problem: "Password reset flow detected"

**Cause**: Twitter detected automated login and redirected to password reset.

**Solutions**:
1. Use cookie-based authentication instead (see Cookie Authentication section below)
2. Try again later (your IP may be temporarily flagged)
3. Manually verify your account

### Problem: "Phone/Email verification screen detected"

**Cause**: Twitter requires additional verification for your account.

**Solution**: Use cookie-based authentication or manually complete verification.

### Problem: "Could not find password input field"

**Cause**: Page structure changed or didn't load properly.

**Solutions**:
1. Enable debug mode to see what's happening
2. Check your internet connection
3. Try cookie-based authentication

### Problem: 403 Forbidden errors when scraping

**Cause**: Not authenticated or rate-limited.

**Solutions**:
1. Verify login was successful (check logs for ✓ marks)
2. Use cookie-based authentication
3. Wait before retrying (rate limit)

## Cookie-Based Authentication (Recommended)

If Selenium login fails, use cookies from your browser:

### Get Cookies from Browser

1. Open Chrome and log into [x.com](https://x.com)
2. Press F12 (or Cmd+Option+I on Mac) to open DevTools
3. Go to **Application** tab → **Cookies** → `https://x.com`
4. Find these cookies:
   - `ct0` (CSRF token)
   - `auth_token` (Authentication token)
5. Copy their values

### Add to .env

```bash
TWITTER_CT0=your_ct0_value_here
TWITTER_AUTH_TOKEN=your_auth_token_value_here
```

### Benefits

- ✅ No automation detection
- ✅ No CAPTCHA challenges  
- ✅ Faster (no browser startup)
- ✅ More reliable

## Log Messages Explained

### Success Indicators

- `✓ Successfully logged in` - Login completed
- `✓ Essential cookies present` - Got auth_token and ct0
- `✓ Cookies transferred via ...` - Cookies sent to Twikit
- `✓ Cookie authentication successful` - Ready to scrape

### Warning Indicators

- `⚠ Login verification uncertain` - Login may have worked but unsure
- `⚠ Phone/Email verification screen detected` - Twitter wants additional verification
- `⚠ Login completed but essential cookies missing` - Partial success

### Error Indicators

- `✗ Failed to transfer cookies` - Cookie transfer failed
- `✗ Selenium login failed` - Login process failed
- `ERROR Password reset flow detected` - Account verification required

## Advanced Configuration

### Time Window

Change how far back to scrape (default: 24 hours):

```bash
# In settings.py or .env
TWITTER_TIME_WINDOW_HOURS=48  # Last 48 hours
```

### Hashtags

Modify hashtags in `twitter_scraper_twikit.py`:

```python
HASHTAGS = ['#nifty50', '#sensex', '#intraday', '#banknifty']
```

### Minimum Tweets

Change target tweet count:

```python
MIN_TWEETS = 2000  # Adjust as needed
```

## Security Notes

⚠️ **Important**: 
- Never commit `.env` file to git
- Keep credentials secure
- Don't share your cookies with anyone
- Cookies expire - re-extract when needed

## Need Help?

Check the logs for detailed information:

```bash
tail -f scraper.log
```

Or check Django console output for colored logs with detailed status updates.

