#!/usr/bin/env python
"""
Quick test script to verify Twitter login configuration
Run this before starting the scraper to verify everything is set up correctly
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'market_intel.settings')
django.setup()

from django.conf import settings
import logging

# Setup colored logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_configuration():
    """Test if Twitter credentials are configured"""
    print("\n" + "="*60)
    print("Twitter/X Login Configuration Test")
    print("="*60 + "\n")
    
    # Check credentials
    username = getattr(settings, 'TWITTER_USERNAME', None)
    password = getattr(settings, 'TWITTER_PASSWORD', None)
    email = getattr(settings, 'TWITTER_EMAIL', None)
    ct0 = getattr(settings, 'TWITTER_CT0', None)
    auth_token = getattr(settings, 'TWITTER_AUTH_TOKEN', None)
    debug_mode = getattr(settings, 'TWITTER_DEBUG_MODE', False)
    
    print("📋 Configuration Status:\n")
    
    # Method 1: Credentials
    if username and password:
        print(f"✓ Selenium Login: CONFIGURED")
        print(f"  - Username: {username[:3]}***")
        print(f"  - Password: {'*' * len(password)}")
        print(f"  - Email: {email if email else 'Not set'}")
        method_configured = True
    else:
        print(f"✗ Selenium Login: NOT CONFIGURED")
        print(f"  - Add TWITTER_USERNAME and TWITTER_PASSWORD to .env")
        method_configured = False
    
    print()
    
    # Method 2: Cookies
    if ct0 and auth_token:
        print(f"✓ Cookie-Based Auth: CONFIGURED")
        print(f"  - ct0: {ct0[:10]}...")
        print(f"  - auth_token: {auth_token[:10]}...")
        cookie_configured = True
    else:
        print(f"✗ Cookie-Based Auth: NOT CONFIGURED")
        print(f"  - Add TWITTER_CT0 and TWITTER_AUTH_TOKEN to .env")
        cookie_configured = False
    
    print()
    
    # Debug mode
    print(f"🔧 Debug Mode: {'ENABLED (browser will be visible)' if debug_mode else 'DISABLED (headless)'}")
    
    print("\n" + "-"*60 + "\n")
    
    # Recommendations
    if cookie_configured:
        print("✅ Recommended: Cookie-based authentication is configured")
        print("   This is the most reliable method.")
    elif method_configured:
        print("⚠️  Warning: Only Selenium login is configured")
        print("   Twitter may detect automation. Consider using cookies.")
    else:
        print("❌ ERROR: No authentication method configured!")
        print("\n📝 Next Steps:")
        print("   1. Copy .env.example to .env")
        print("   2. Add your Twitter credentials")
        print("   3. Run this test again")
        return False
    
    print("\n" + "-"*60 + "\n")
    
    # Test import
    print("🔍 Testing imports...\n")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        from twikit import Client
        print("✓ Selenium: OK")
        print("✓ Twikit: OK")
        print("✓ WebDriver Manager: OK")
    except ImportError as e:
        print(f"✗ Import Error: {e}")
        print("\n📝 Run: pip install -r requirements.txt")
        return False
    
    print("\n" + "="*60)
    print("✅ Configuration test passed!")
    print("="*60 + "\n")
    
    print("Next steps:")
    print("  1. Start the server: python manage.py runserver")
    print("  2. Trigger scraping: curl -X POST http://127.0.0.1:8000/api/scrape/")
    print("  3. Check logs for login status\n")
    
    if debug_mode:
        print("⚠️  Note: Debug mode is ON - browser window will be visible")
        print("   Set TWITTER_DEBUG_MODE=False in .env for headless mode\n")
    
    return True

if __name__ == '__main__':
    try:
        success = test_configuration()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

