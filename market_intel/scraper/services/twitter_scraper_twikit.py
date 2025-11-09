"""
Twitter scraper using Selenium + Twikit hybrid approach
Maintains session and cookies for reliable authentication
"""
import asyncio
import hashlib
import logging
import re
import time
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import urlparse

import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from twikit import Client
from django.conf import settings

logger = logging.getLogger(__name__)


class TwitterScraperTwikit:
    """Hybrid Twitter scraper: Selenium for session/cookies, Twikit for scraping"""
    
    HASHTAGS = ['#nifty50', '#sensex', '#intraday', '#banknifty']
    MIN_TWEETS = 2000
    TIME_WINDOW_HOURS = 24  # Last 24 hours per assignment
    
    def __init__(self, headless: bool = None):
        """Initialize scraper with Selenium + Twikit"""
        # Check if DEBUG mode is enabled in settings
        if headless is None:
            headless = not getattr(settings, 'TWITTER_DEBUG_MODE', False)
        self.headless = headless
        self.client = None
        self.driver = None
        self.authenticated = False
        self.cookies = {}
        
        # Get credentials from settings
        self.username = getattr(settings, 'TWITTER_USERNAME', None)
        self.password = getattr(settings, 'TWITTER_PASSWORD', None)
        self.email = getattr(settings, 'TWITTER_EMAIL', None)
        
        # Get cookie-based auth from settings
        self.ct0 = getattr(settings, 'TWITTER_CT0', None)
        self.auth_token = getattr(settings, 'TWITTER_AUTH_TOKEN', None)
        self.cookie_file = getattr(settings, 'TWITTER_COOKIE_FILE', None)
        self.cookies_json = getattr(settings, 'TWITTER_COOKIES', None)
        
        # IP Rotation / Proxy configuration
        self.proxies = self._load_proxies()
        self.current_proxy_index = 0
        self.proxy_rotation_enabled = len(self.proxies) > 0
        
        # Debug: Log credential status (without exposing values)
        if self.username:
            logger.info(f"Credentials loaded: username={self.username[:3]}***, email={'set' if self.email else 'not set'}, password={'set' if self.password else 'not set'}")
        if self.ct0 or self.auth_token:
            logger.info(f"Cookie-based auth available: ct0={'set' if self.ct0 else 'not set'}, auth_token={'set' if self.auth_token else 'not set'}")
        if not self.username and not self.ct0:
            logger.warning("No Twitter credentials found in settings. Check your .env file.")
        if self.proxy_rotation_enabled:
            logger.info(f"IP rotation enabled: {len(self.proxies)} proxy/proxies configured")
        else:
            logger.info("IP rotation disabled: No proxies configured")
    
    def _load_proxies(self) -> List[Dict[str, str]]:
        """Load proxy configuration from settings"""
        proxies = []
        
        # Method 1: Single proxy string (format: http://user:pass@host:port or http://host:port)
        proxy_string = getattr(settings, 'TWITTER_PROXY', None)
        if proxy_string:
            proxies.append(self._parse_proxy_string(proxy_string))
        
        # Method 2: List of proxy strings (comma-separated or newline-separated)
        proxy_list = getattr(settings, 'TWITTER_PROXIES', None)
        if proxy_list:
            if isinstance(proxy_list, str):
                # Handle comma or newline separated
                proxy_strings = [p.strip() for p in proxy_list.replace('\n', ',').split(',') if p.strip()]
                for proxy_str in proxy_strings:
                    proxies.append(self._parse_proxy_string(proxy_str))
            elif isinstance(proxy_list, list):
                for proxy_str in proxy_list:
                    if isinstance(proxy_str, str):
                        proxies.append(self._parse_proxy_string(proxy_str))
        
        # Method 3: Proxy file path (one proxy per line)
        proxy_file = getattr(settings, 'TWITTER_PROXY_FILE', None)
        if proxy_file:
            try:
                with open(proxy_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            proxies.append(self._parse_proxy_string(line))
            except Exception as e:
                logger.warning(f"Could not load proxy file {proxy_file}: {e}")
        
        return proxies
    
    def _parse_proxy_string(self, proxy_string: str) -> Dict[str, str]:
        """Parse a proxy string into a dictionary"""
        # Remove any whitespace
        proxy_string = proxy_string.strip()
        
        # Parse URL
        parsed = urlparse(proxy_string)
        
        proxy_dict = {
            'scheme': parsed.scheme or 'http',
            'host': parsed.hostname or '',
            'port': str(parsed.port) if parsed.port else '8080',
            'username': parsed.username or '',
            'password': parsed.password or '',
        }
        
        # Build proxy URL for Selenium
        if proxy_dict['username'] and proxy_dict['password']:
            proxy_url = f"{proxy_dict['scheme']}://{proxy_dict['username']}:{proxy_dict['password']}@{proxy_dict['host']}:{proxy_dict['port']}"
        else:
            proxy_url = f"{proxy_dict['scheme']}://{proxy_dict['host']}:{proxy_dict['port']}"
        
        proxy_dict['url'] = proxy_url
        proxy_dict['original'] = proxy_string
        
        return proxy_dict
    
    def _get_next_proxy(self) -> Optional[Dict[str, str]]:
        """Get the next proxy in rotation"""
        if not self.proxy_rotation_enabled or not self.proxies:
            return None
        
        # Get rotation strategy from settings
        rotation_strategy = getattr(settings, 'TWITTER_PROXY_ROTATION', 'round_robin').lower()
        
        if rotation_strategy == 'random':
            proxy = random.choice(self.proxies)
            logger.info(f"Using random proxy: {proxy['host']}:{proxy['port']}")
        else:  # round_robin (default)
            proxy = self.proxies[self.current_proxy_index]
            proxy_num = self.current_proxy_index + 1
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
            logger.info(f"Using proxy {proxy_num}/{len(self.proxies)}: {proxy['host']}:{proxy['port']}")
        
        return proxy
    
    def _rotate_proxy(self):
        """Manually rotate to next proxy"""
        if self.proxy_rotation_enabled and self.proxies:
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
            logger.info(f"Rotated to proxy {self.current_proxy_index + 1}/{len(self.proxies)}")
    
    def _init_selenium(self, retry_with_new_proxy: bool = False) -> webdriver.Chrome:
        """Initialize undetected Chrome WebDriver with stealth settings and optional proxy"""
        options = Options()
        if self.headless:
            options.add_argument('--headless=new')  # Use new headless mode
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        # Add preferences to make it look more like a real browser
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2
        }
        options.add_experimental_option("prefs", prefs)
        
        # Add proxy if IP rotation is enabled
        proxy = None
        if self.proxy_rotation_enabled:
            if retry_with_new_proxy:
                # Rotate to next proxy on retry
                self._rotate_proxy()
            proxy = self._get_next_proxy()
            
            if proxy:
                # Configure proxy for Chrome
                proxy_server = f"{proxy['host']}:{proxy['port']}"
                options.add_argument(f'--proxy-server={proxy_server}')
                logger.info(f"Configured proxy: {proxy['host']}:{proxy['port']}")
                
                # Note: For authenticated proxies, you may need to use IP whitelisting
                # or configure proxy authentication separately
                if proxy['username'] and proxy['password']:
                    logger.info("Proxy with authentication detected - ensure proxy supports IP whitelisting")
        
        # Use undetected-chromedriver to bypass bot detection
        # It automatically handles webdriver hiding and other stealth features
        try:
            driver = uc.Chrome(
                options=options,
                headless=self.headless,
                version_main=None,  # Auto-detect Chrome version
                use_subprocess=True,  # Use subprocess for better stealth
            )
            logger.info("Initialized undetected Chrome driver (bot detection bypass enabled)")
        except Exception as e:
            logger.warning(f"Failed to initialize undetected Chrome driver: {e}")
            logger.info("Falling back to standard Chrome driver")
            # Fallback to standard Chrome driver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        
        return driver
    
    def _check_for_login_error(self) -> bool:
        """Check if Twitter is showing a login error/block message"""
        try:
            page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            page_text_full = self.driver.find_element(By.TAG_NAME, 'body').text  # Keep original case for display
            error_keywords = [
                'could not log you in now',
                'please try again later',
                'something went wrong',
                'try again later',
                'temporarily unavailable',
                'account temporarily locked',
                'too many requests'
            ]
            
            # Find which specific error keyword was detected
            detected_error = None
            for keyword in error_keywords:
                if keyword in page_text:
                    detected_error = keyword
                    break
            
            if detected_error:
                logger.error("=" * 80)
                logger.error("Twitter login error detected!")
                logger.error(f"Detected error keyword: '{detected_error}'")
                logger.error(f"Current URL: {self.driver.current_url}")
                logger.error(f"Page title: {self.driver.title}")
                logger.error("-" * 80)
                
                # Try to extract the actual error message from the page
                try:
                    # Look for error messages in common Twitter error containers
                    error_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                        '[role="alert"], [data-testid*="error"], .error, [class*="error"], [class*="Error"]')
                    if error_elements:
                        for elem in error_elements[:3]:  # Check first 3 error elements
                            error_text = elem.text.strip()
                            if error_text:
                                logger.error(f"Error element text: {error_text}")
                    
                    # Also try to find text containing the error keyword
                    error_text_snippet = page_text_full
                    if detected_error in page_text_full.lower():
                        # Find the sentence/paragraph containing the error
                        sentences = page_text_full.split('.')
                        for sentence in sentences:
                            if detected_error in sentence.lower():
                                logger.error(f"Error message found: {sentence.strip()}")
                                break
                except:
                    pass
                
                logger.error("-" * 80)
                logger.error("Full page text (first 500 chars):")
                logger.error(page_text_full[:500])
                logger.error("-" * 80)
                
                # Save screenshot for debugging
                try:
                    screenshot_path = 'login_error_detected.png'
                    self.driver.save_screenshot(screenshot_path)
                    logger.error(f"Screenshot saved: {screenshot_path}")
                except Exception as e:
                    logger.error(f"Could not save screenshot: {e}")
                
                logger.error("Twitter is blocking the login attempt. Possible reasons:")
                logger.error("  1. Too many login attempts")
                logger.error("  2. Account temporarily locked")
                logger.error("  3. IP address flagged")
                logger.error("  4. Automation detected")
                logger.error("  5. Rate limiting")
                logger.error("Recommendation: Wait before retrying or use cookie-based authentication")
                logger.error("=" * 80)
                return True  # Error found
            return False  # No error
        except Exception as e:
            logger.debug(f"Error checking for login errors: {e}")
            return False
    
    def _handle_unusual_activity_screen(self) -> bool:
        """Handle Twitter's 'unusual login activity' screen that asks for username/phone"""
        try:
            # Get current page text to check for unusual activity screen
            page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            unusual_activity_keywords = ['unusual login activity', 'enter your phone number or username', 'phone or username']
            
            if not any(keyword in page_text for keyword in unusual_activity_keywords):
                return False  # Not on unusual activity screen
            
            logger.info("Detected 'unusual login activity' screen. Entering username...")
            
            # Find the input field for phone/username
            verification_selectors = [
                'input[data-testid="ocfEnterTextTextInput"]',
                'input[name="text"]',
                'input[type="text"]',
                'input[placeholder*="Phone or username"]',
                'input[placeholder*="phone"]',
            ]
            
            verification_input = None
            for selector in verification_selectors:
                try:
                    verification_input = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if verification_input:
                        logger.info(f"Found verification input field with selector: {selector}")
                        break
                except:
                    continue
            
            if not verification_input:
                logger.error("Could not find verification input field on unusual activity screen")
                return False
            
            if not self.username:
                logger.error("Username required for unusual activity verification but not configured!")
                return False
            
            # Enter username
            logger.info(f"Entering username for unusual activity verification: {self.username[:3]}***")
            verification_input.clear()
            # Type username slowly
            for char in self.username:
                verification_input.send_keys(char)
                time.sleep(0.1)
            time.sleep(1)
            
            # Click Next button
            logger.info("Clicking Next button after entering username...")
            next_selectors = [
                ('XPATH', '//span[text()="Next"]'),
                ('XPATH', '//div[@role="button"]//span[text()="Next"]'),
                ('XPATH', '//button//span[text()="Next"]'),
            ]
            
            next_clicked = False
            for method, selector in next_selectors:
                try:
                    if method == 'XPATH':
                        next_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        next_button = self.driver.find_element(By.XPATH, '//div[@role="button"][.//span[text()="Next"]]')
                    next_button.click()
                    next_clicked = True
                    logger.info("Next button clicked after username entry")
                    time.sleep(5)  # Wait for next screen to load
                    
                    # Check for errors after clicking Next
                    if self._check_for_login_error():
                        logger.error("Login error detected after clicking Next on unusual activity screen")
                        return False
                    
                    break
                except Exception as e:
                    logger.debug(f"Next button selector {selector} failed: {e}")
                    continue
            
            if not next_clicked:
                logger.warning("Could not click Next button on unusual activity screen")
                return False
            
            return True  # Successfully handled
            
        except Exception as e:
            logger.error(f"Error handling unusual login activity screen: {e}")
            return False
    
    def _login_with_selenium(self, max_retries: int = None) -> bool:
        """Login to Twitter using Selenium with human-like behavior and optional proxy rotation retries"""
        if not self.username or not self.password:
            logger.warning("No credentials provided, skipping login")
            return False
        
        # Get max retries from settings or use default
        if max_retries is None:
            max_retries = getattr(settings, 'TWITTER_LOGIN_MAX_RETRIES', 1)
            if self.proxy_rotation_enabled and len(self.proxies) > 1:
                # If we have multiple proxies, allow retries up to proxy count
                max_retries = min(max_retries, len(self.proxies))
        
        retry_count = 0
        last_exception = None
        
        while retry_count <= max_retries:
            try:
                # Close previous driver if exists
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                
                # Initialize with new proxy if retrying
                retry_with_new_proxy = retry_count > 0 and self.proxy_rotation_enabled
                self.driver = self._init_selenium(retry_with_new_proxy=retry_with_new_proxy)
                
                if retry_count > 0:
                    logger.info(f"Retry attempt {retry_count}/{max_retries} with {'new proxy' if retry_with_new_proxy else 'same settings'}")
                    time.sleep(2)  # Brief delay before retry
                
                logger.info(f"Logging in to Twitter as {self.username[:3]}***")
                
                # Navigate to main Twitter page first (more human-like)
                logger.info("Loading Twitter homepage...")
                self.driver.get("https://x.com")
                time.sleep(3)
                
                # Then navigate to login page
                logger.info("Navigating to login page...")
                self.driver.get("https://x.com/i/flow/login")
                time.sleep(5)  # Wait for page to fully load
                
                # Enter username/email - try multiple selectors
                logger.info("Looking for username input field...")
                username_selectors = [
                    'input[autocomplete="username"]',
                    'input[type="text"]',
                    'input[name="text"]',
                    'input[data-testid="ocfEnterTextTextInput"]'
                ]
                username_input = None
                for selector in username_selectors:
                    try:
                        username_input = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        logger.info(f"Found username field with selector: {selector}")
                        break
                    except Exception as e:
                        logger.debug(f"Username selector {selector} failed: {e}")
                        continue
                
                if not username_input:
                    # Save screenshot for debugging
                    try:
                        self.driver.save_screenshot('login_debug_username.png')
                        logger.error("Screenshot saved: login_debug_username.png")
                    except:
                        pass
                    raise Exception("Could not find username input field")
                
                # Type slowly like a human
                username_input.clear()
                username_to_use = self.email or self.username
                for char in username_to_use:
                    username_input.send_keys(char)
                    time.sleep(0.1)  # Small delay between keystrokes
                time.sleep(1)
                
                # Click next - try multiple methods
                logger.info("Clicking Next button...")
                next_selectors = [
                    ('XPATH', '//span[text()="Next"]'),
                    ('XPATH', '//div[@role="button"]//span[text()="Next"]'),
                    ('XPATH', '//button//span[text()="Next"]'),
                    ('CSS_SELECTOR', 'div[role="button"]'),
                ]
                next_clicked = False
                for method, selector in next_selectors:
                    try:
                        if method == 'XPATH':
                            next_button = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.XPATH, selector))
                            )
                        else:
                            next_button = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                            )
                        next_button.click()
                        next_clicked = True
                        logger.info("Next button clicked")
                        break
                    except Exception as e:
                        logger.debug(f"Next button selector {selector} failed: {e}")
                        continue
                
                if not next_clicked:
                    logger.warning("Could not click Next button, trying to continue...")
                
                time.sleep(3)
                
                # Check for unusual activity screen (can appear after username entry)
                self._handle_unusual_activity_screen()
                
                # Check for login errors
                if self._check_for_login_error():
                    raise Exception("Twitter login blocked - error detected after username entry. Wait before retrying or use cookie-based authentication.")
                
                # Check for CAPTCHA or other blockers
                try:
                    captcha_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="challenge"]')
                    if captcha_elements:
                        logger.warning("CAPTCHA detected. Please complete manually or use cookie-based auth.")
                        raise Exception("CAPTCHA detected - manual intervention required")
                except:
                    pass
                
                # Enter password - wait longer and try more selectors
                logger.info("Looking for password input field...")
                time.sleep(3)  # Extra wait for password field to appear
                
                # Check if we're on a different screen (phone/email verification, password reset, etc.)
                current_url_check = self.driver.current_url
                page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
                
                # Detect password reset flow - Twitter redirects here when it detects automation
                if 'password_reset' in current_url_check or 'account_access' in current_url_check:
                    logger.error("Twitter redirected to password reset/verification flow.")
                    logger.error("This typically happens due to:")
                    logger.error("  1. Unusual login pattern detected")
                    logger.error("  2. Account locked/suspended")
                    logger.error("  3. IP address flagged")
                    logger.error("Please manually verify your account or try cookie-based authentication.")
                    raise Exception("Account verification required - automated login blocked")
                
                if 'phone' in page_text or 'email' in page_text or 'verify' in page_text:
                    logger.info("Email/Phone verification screen detected. Entering email...")
                    
                    # Try to find the verification input field and enter email
                    try:
                        # Look for the verification input field (usually asks for email or phone)
                        verification_selectors = [
                            'input[data-testid="ocfEnterTextTextInput"]',
                            'input[name="text"]',
                            'input[type="text"]',
                            'input[autocomplete="email"]'
                        ]
                        
                        verification_input = None
                        for selector in verification_selectors:
                            try:
                                verification_input = WebDriverWait(self.driver, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                )
                                if verification_input:
                                    break
                            except:
                                continue
                        
                        if verification_input and self.email:
                            logger.info(f"Entering email for verification: {self.email}")
                            verification_input.clear()
                            # Type email slowly
                            for char in self.email:
                                verification_input.send_keys(char)
                                time.sleep(0.1)
                            time.sleep(1)
                            
                            # Click Next button
                            logger.info("Clicking Next after email verification...")
                            next_selectors = [
                                ('XPATH', '//span[text()="Next"]'),
                                ('XPATH', '//div[@role="button"]//span[text()="Next"]'),
                                ('XPATH', '//button//span[text()="Next"]'),
                            ]
                            
                            for method, selector in next_selectors:
                                try:
                                    next_button = WebDriverWait(self.driver, 5).until(
                                        EC.element_to_be_clickable((By.XPATH, selector))
                                    )
                                    next_button.click()
                                    logger.info("Next button clicked after email verification")
                                    break
                                except:
                                    continue
                        else:
                            if not self.email:
                                logger.error("Email verification required but no email configured!")
                            else:
                                logger.warning("Could not find verification input field")
                    except Exception as e:
                        logger.error(f"Error during email verification: {e}")
                
                # Wait for page to stabilize after email verification
                logger.info("Waiting for password screen to load...")
                time.sleep(5)  # Increased wait time for page to load
                
                # Check what screen we're on now
                current_url_after_email = self.driver.current_url
                page_text_after_email = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
                logger.info(f"After email verification - URL: {current_url_after_email}")
                logger.info(f"Page contains: {page_text_after_email[:200]}...")
                
                # Check for login errors (e.g., "could not log you in now")
                if self._check_for_login_error():
                    raise Exception("Twitter login blocked - 'could not log you in now' error detected. Wait before retrying or use cookie-based authentication.")
                
                # Check for "unusual login activity" screen (can appear after email verification)
                if self._handle_unusual_activity_screen():
                    # Update page text after handling unusual activity screen
                    try:
                        time.sleep(2)  # Wait for page to update
                        page_text_after_email = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
                        current_url_after_email = self.driver.current_url
                        logger.info(f"After unusual activity verification - URL: {current_url_after_email}")
                    except:
                        pass
                    
                    # Check for errors after handling unusual activity
                    if self._check_for_login_error():
                        raise Exception("Twitter login blocked - error detected after unusual activity verification. Wait before retrying or use cookie-based authentication.")
                
                # Check for additional verification requirements
                additional_verification_keywords = ['phone', 'verify your phone', 'two-factor', '2fa', 'verification code', 'enter code']
                if any(keyword in page_text_after_email for keyword in additional_verification_keywords):
                    logger.warning("Additional verification required (phone/2FA). This may block automated login.")
                    logger.warning("Consider using cookie-based authentication instead.")
                
                # Check for CAPTCHA or security challenges
                try:
                    captcha_indicators = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="challenge"], iframe[src*="captcha"], iframe[src*="recaptcha"]')
                    if captcha_indicators:
                        logger.error("CAPTCHA or security challenge detected after email verification")
                        logger.error("Twitter is likely detecting automation. Use cookie-based auth instead.")
                        raise Exception("CAPTCHA detected - automation blocked")
                except:
                    pass
                
                # Check for unusual activity screen one more time before password (can appear at any point)
                self._handle_unusual_activity_screen()
                
                # Check for login errors before password entry
                if self._check_for_login_error():
                    raise Exception("Twitter login blocked - error detected before password entry. Wait before retrying or use cookie-based authentication.")
                
                # Try to find password field - check for iframes first
                password_input = None
                
                # Wait a bit more for password field to appear (Twitter sometimes loads it dynamically)
                logger.info("Waiting for password field to appear...")
                time.sleep(3)
                
                # Method 1: Check main document with longer timeout
                password_selectors = [
                    'input[name="password"]',
                    'input[type="password"]',
                    'input[autocomplete="current-password"]',
                    'input[data-testid="ocfEnterTextTextInput"]',
                    'input[name="passwd"]',
                ]
            
                for selector in password_selectors:
                    try:
                        # Wait for element to be both present AND visible/clickable
                        password_input = WebDriverWait(self.driver, 15).until(  # Increased timeout
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        # Verify it's actually a password field
                        field_type = password_input.get_attribute('type')
                        if field_type == 'password' or 'password' in selector.lower():
                            logger.info(f"Found password field with selector: {selector}")
                            break
                        else:
                            # If it's the ocfEnterTextTextInput, check if we're on password screen
                            if selector == 'input[data-testid="ocfEnterTextTextInput"]':
                                # Check if placeholder or label indicates password
                                placeholder = password_input.get_attribute('placeholder') or ''
                                aria_label = password_input.get_attribute('aria-label') or ''
                                # Also check surrounding text
                                try:
                                    parent = password_input.find_element(By.XPATH, './ancestor::div[1]')
                                    parent_text = parent.text.lower()
                                except:
                                    parent_text = ''
                                
                                if ('password' in placeholder.lower() or 
                                    'password' in aria_label.lower() or
                                    'password' in parent_text):
                                    logger.info(f"Found password field via placeholder/label/context: {selector}")
                                    break
                            password_input = None
                    except Exception as e:
                        # If element_to_be_clickable fails, try presence_of_element_located
                        try:
                            password_input = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            # Check if it becomes visible after a short wait
                            time.sleep(1)
                            if password_input.is_displayed():
                                field_type = password_input.get_attribute('type')
                                if field_type == 'password' or 'password' in selector.lower():
                                    logger.info(f"Found password field with selector: {selector} (after visibility wait)")
                                    break
                        except:
                            pass
                        logger.debug(f"Password selector {selector} failed: {e}")
                        continue
            
                # Method 2: Check iframes if not found in main document
                if not password_input:
                    try:
                        iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
                        logger.info(f"Checking {len(iframes)} iframes for password field...")
                        for iframe in iframes:
                            try:
                                self.driver.switch_to.frame(iframe)
                                for selector in password_selectors:
                                    try:
                                        password_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                                        if password_input:
                                            logger.info(f"Found password field in iframe with selector: {selector}")
                                            break
                                    except:
                                        continue
                                if password_input:
                                    break
                                self.driver.switch_to.default_content()
                            except:
                                self.driver.switch_to.default_content()
                                continue
                    except Exception as e:
                        logger.debug(f"Iframe check failed: {e}")
            
                # Method 3: Try to interact with the text input to see if it's the password field
                if not password_input:
                    try:
                        # Twitter sometimes uses the same input field but changes its type dynamically
                        text_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"], input[name="text"], input[type="text"]')
                        for text_input in text_inputs:
                            try:
                                # Check if clicking/focusing reveals it's a password field
                                text_input.click()
                                time.sleep(0.5)
                                # Check if type changed or if there's a password-related attribute
                                input_type = text_input.get_attribute('type')
                                placeholder = text_input.get_attribute('placeholder') or ''
                                aria_label = text_input.get_attribute('aria-label') or ''
                                name_attr = text_input.get_attribute('name') or ''
                                
                                # Check surrounding text for password indicators
                                try:
                                    parent = text_input.find_element(By.XPATH, './ancestor::div[contains(@class, "r-")]')
                                    parent_text = parent.text.lower()
                                except:
                                    parent_text = ''
                                
                                # If any indicator suggests password, try to use it
                                password_indicators = ['password', 'pass', 'pwd']
                                if (any(ind in placeholder.lower() for ind in password_indicators) or
                                    any(ind in aria_label.lower() for ind in password_indicators) or
                                    any(ind in parent_text for ind in password_indicators) or
                                    'password' in name_attr.lower()):
                                    logger.info("Found password field via context/attributes")
                                    password_input = text_input
                                    # Try to change type to password if possible
                                    try:
                                        self.driver.execute_script("arguments[0].type = 'password';", text_input)
                                    except:
                                        pass
                                    break
                            except:
                                continue
                    except Exception as e:
                        logger.debug(f"Method 3 (text input interaction) failed: {e}")
            
                # Method 4: Try XPath as fallback
                if not password_input:
                    try:
                        password_input = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, '//input[@type="password"]'))
                        )
                        logger.info("Found password field using XPath")
                    except Exception as e:
                        # Method 5: Try finding by placeholder text or surrounding text
                        try:
                            # Look for input near password-related text
                            password_input = self.driver.find_element(By.XPATH, 
                                '//input[(@placeholder and (contains(@placeholder, "password") or contains(@placeholder, "Password"))) or '
                                '(ancestor::div[contains(., "password") or contains(., "Password")])]')
                            # Verify it's actually usable
                            if password_input and password_input.is_displayed():
                                logger.info("Found password field by placeholder/context")
                                # Try to set type to password
                                try:
                                    self.driver.execute_script("arguments[0].type = 'password';", password_input)
                                except:
                                    pass
                            else:
                                password_input = None
                        except:
                            pass
            
                if not password_input:
                    # Save screenshot and page info for debugging
                    try:
                        self.driver.save_screenshot('login_debug_password.png')
                        logger.error(f"Screenshot saved: login_debug_password.png")
                        logger.error(f"Current URL: {self.driver.current_url}")
                        logger.error(f"Page title: {self.driver.title}")
                        
                        # Log all input fields found with more details
                        all_inputs = self.driver.find_elements(By.TAG_NAME, 'input')
                        logger.error(f"Found {len(all_inputs)} input fields on page")
                        for inp in all_inputs[:10]:  # Log first 10
                            inp_type = inp.get_attribute('type')
                            inp_name = inp.get_attribute('name')
                            inp_id = inp.get_attribute('id')
                            inp_placeholder = inp.get_attribute('placeholder')
                            inp_aria_label = inp.get_attribute('aria-label')
                            inp_testid = inp.get_attribute('data-testid')
                            logger.error(f"  Input: type={inp_type}, name={inp_name}, id={inp_id}, "
                                       f"placeholder={inp_placeholder}, aria-label={inp_aria_label}, "
                                       f"testid={inp_testid}")
                        
                        # Log page text to understand what screen we're on
                        try:
                            body_text = self.driver.find_element(By.TAG_NAME, 'body').text
                            logger.error(f"Page text (first 500 chars): {body_text[:500]}")
                            
                            # Check for common error messages or alternative flows
                            if 'verification code' in body_text.lower() or 'enter code' in body_text.lower():
                                logger.error("Twitter is asking for a verification code instead of password.")
                                logger.error("This usually means 2FA is enabled or Twitter detected suspicious activity.")
                            elif 'phone' in body_text.lower() and 'verify' in body_text.lower():
                                logger.error("Twitter is asking for phone verification.")
                            elif 'suspended' in body_text.lower() or 'locked' in body_text.lower():
                                logger.error("Account may be suspended or locked.")
                            elif 'captcha' in body_text.lower() or 'robot' in body_text.lower():
                                logger.error("CAPTCHA or bot detection is blocking the login.")
                        except:
                            pass
                    except Exception as e:
                        logger.error(f"Error saving debug info: {e}")
                
                error_msg = ("Could not find password input field after trying all methods. "
                           "Twitter may be showing a different screen (verification code, phone verification, "
                           "or CAPTCHA). Check login_debug_password.png for details. "
                           "Consider using cookie-based authentication (TWITTER_CT0 and TWITTER_AUTH_TOKEN) instead.")
                raise Exception(error_msg)
            
                # Type password slowly like a human
                password_input.clear()
                for char in self.password:
                    password_input.send_keys(char)
                time.sleep(0.15)  # Slightly slower for password
                time.sleep(2)
            
                logger.info("Password entered successfully")
            
                # Click login
                logger.info("Clicking Log in button...")
                login_selectors = [
                    ('XPATH', '//span[text()="Log in"]'),
                    ('XPATH', '//div[@role="button"]//span[text()="Log in"]'),
                    ('XPATH', '//button//span[text()="Log in"]'),
                    ('XPATH', '//span[text()="Log in"]/ancestor::div[@role="button"]'),
                ]
                login_clicked = False
                for method, selector in login_selectors:
                    try:
                        login_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        login_button.click()
                        login_clicked = True
                        logger.info("Log in button clicked")
                        break
                    except Exception as e:
                        logger.debug(f"Login button selector {selector} failed: {e}")
                        continue
            
                if not login_clicked:
                    logger.warning("Could not click Log in button")
            
                # Wait for login to complete and check for success
                logger.info("Waiting for login to complete...")
                time.sleep(5)
            
                # Check for authentication success - wait for home feed or redirect
                try:
                    # Wait for either home timeline or other success indicators
                    logger.info("Checking for successful login...")
                    
                    # Wait up to 15 seconds for login to complete
                    for i in range(15):
                        current_url = self.driver.current_url
                        
                        # Check URL indicators
                        if any(indicator in current_url for indicator in ['home', 'explore', 'notifications']):
                            logger.info(f"Login successful - redirected to: {current_url}")
                            break
                        
                        # Check for error messages
                        page_source = self.driver.page_source.lower()
                        if any(err in page_source for err in ['wrong password', 'incorrect', 'suspended', 'locked']):
                            logger.error("Login failed - incorrect credentials or account issue")
                            raise Exception("Invalid credentials or account locked")
                        
                        time.sleep(1)
                    
                    # Double check with page elements
                    try:
                        # Look for logged-in indicators
                        profile_nav = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="SideNav_AccountSwitcher_Button"]')
                        compose_button = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="SideNav_NewTweet_Button"]')
                        
                        if profile_nav or compose_button:
                            logger.info("Verified login - found user interface elements")
                        else:
                            logger.warning("Login verification uncertain - UI elements not found")
                    except:
                        pass
                    
                    # Extract cookies
                    selenium_cookies = self.driver.get_cookies()
                    self.cookies = {cookie['name']: cookie['value'] for cookie in selenium_cookies}
                    
                    # Check for essential cookies
                    if 'auth_token' in self.cookies or 'ct0' in self.cookies:
                        logger.info(f"✓ Successfully logged in - extracted {len(self.cookies)} cookies")
                        logger.info(f"✓ Essential cookies present: auth_token={'✓' if 'auth_token' in self.cookies else '✗'}, ct0={'✓' if 'ct0' in self.cookies else '✗'}")
                        return True
                    else:
                        logger.warning("Login completed but essential cookies missing")
                        logger.info(f"Cookies found: {list(self.cookies.keys())}")
                        # Still return True if we have any cookies
                        return len(self.cookies) > 0
                    
                except Exception as inner_e:
                    logger.error(f"Error during login verification: {inner_e}")
                    # Try to extract cookies anyway
                    try:
                        selenium_cookies = self.driver.get_cookies()
                        self.cookies = {cookie['name']: cookie['value'] for cookie in selenium_cookies}
                        if self.cookies:
                            logger.info(f"Extracted {len(self.cookies)} cookies despite verification error")
                            return True
                    except:
                        pass
                    return False
                
            except Exception as e:
                last_exception = e
                logger.error(f"Selenium login failed (attempt {retry_count + 1}/{max_retries + 1}): {e}")
                
                # Save screenshot for debugging
                try:
                    if self.driver:
                        self.driver.save_screenshot(f'login_error_attempt_{retry_count + 1}.png')
                        logger.error(f"Screenshot saved: login_error_attempt_{retry_count + 1}.png")
                except:
                    pass
                
                # Clean up driver
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                    self.driver = None
                
                # Check if we should retry
                retry_count += 1
                if retry_count <= max_retries:
                    # Check if error is retryable (not authentication errors)
                    error_str = str(e).lower()
                    non_retryable_errors = ['wrong password', 'incorrect', 'invalid credentials', 'account locked', 'suspended']
                    if any(err in error_str for err in non_retryable_errors):
                        logger.error("Non-retryable error detected. Stopping retries.")
                        break
                    
                    # Check if we have proxies to rotate
                    if self.proxy_rotation_enabled and len(self.proxies) > 1:
                        logger.info(f"Will retry with next proxy (attempt {retry_count + 1}/{max_retries + 1})")
                    else:
                        logger.info(f"Will retry login (attempt {retry_count + 1}/{max_retries + 1})")
                    
                    # Wait before retry (exponential backoff)
                    wait_time = min(2 ** retry_count, 10)  # Max 10 seconds
                    time.sleep(wait_time)
                else:
                    logger.error(f"Max retries ({max_retries + 1}) reached. Login failed.")
                    break
        
        # If we exhausted all retries, return False
        if last_exception:
            logger.error(f"Final login failure after {retry_count} retries: {last_exception}")
        return False
    
    def _transfer_cookies_to_twikit(self) -> bool:
        """Transfer cookies from Selenium to Twikit client"""
        if not self.cookies:
            logger.warning("No cookies available to transfer")
            return False
        
        try:
            if not self.client:
                self.client = Client()
            
            logger.info(f"Transferring {len(self.cookies)} cookies to Twikit...")
            
            # Method 1: Use Twikit's set_cookies if available
            if hasattr(self.client, 'set_cookies'):
                try:
                    self.client.set_cookies(self.cookies)
                    self.authenticated = True
                    logger.info("✓ Cookies transferred via set_cookies()")
                    return True
                except Exception as e:
                    logger.debug(f"set_cookies failed: {e}")
            
            # Method 2: Access internal httpx client (most reliable for Twikit)
            client_attrs = ['_client', 'client', 'http_client', '_http_client']
            for attr in client_attrs:
                if hasattr(self.client, attr):
                    try:
                        http_client = getattr(self.client, attr)
                        if http_client and hasattr(http_client, 'cookies'):
                            # Set each cookie individually
                            for name, value in self.cookies.items():
                                if hasattr(http_client.cookies, 'set'):
                                    http_client.cookies.set(name, value, domain='.x.com')
                                    http_client.cookies.set(name, value, domain='.twitter.com')
                            
                            self.authenticated = True
                            logger.info(f"✓ Cookies transferred via {attr}.cookies")
                            return True
                    except Exception as e:
                        logger.debug(f"Cookie transfer via {attr} failed: {e}")
                        continue
            
            # Method 3: Create cookie jar manually
            try:
                import httpx
                from http.cookiejar import Cookie
                from datetime import datetime
                
                # Create new httpx client with cookies
                cookie_jar = httpx.Cookies()
                for name, value in self.cookies.items():
                    cookie_jar.set(name, value, domain='.x.com')
                    cookie_jar.set(name, value, domain='.twitter.com')
                
                # Replace Twikit's client
                self.client._client = httpx.AsyncClient(cookies=cookie_jar, follow_redirects=True)
                self.authenticated = True
                logger.info("✓ Created new httpx client with cookies")
                return True
            except Exception as e:
                logger.debug(f"Manual cookie jar creation failed: {e}")
            
            # Method 4: Set cookies via headers (last resort)
            if hasattr(self.client, 'headers'):
                try:
                    cookie_header = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                    if not hasattr(self.client, 'headers'):
                        self.client.headers = {}
                    self.client.headers['Cookie'] = cookie_header
                    self.authenticated = True
                    logger.info("✓ Cookies set via headers (fallback)")
                    return True
                except Exception as e:
                    logger.debug(f"Header method failed: {e}")
            
            logger.error("✗ Failed to transfer cookies to Twikit using all methods")
            return False
            
        except Exception as e:
            logger.error(f"✗ Cookie transfer error: {e}")
            return False
    
    async def _search_tweets_async(self, query: str, count: int = 500) -> List[Dict]:
        """Search tweets using Twikit"""
        if not self.client:
            self.client = Client()
        
        try:
            results = await self.client.search_tweet(query, product='Latest', count=count)
            return self._process_tweets(results)
        except Exception as e:
            logger.error(f"Search failed for {query}: {e}")
            return []
    
    def _process_tweets(self, tweets) -> List[Dict]:
        """Process Twikit tweet objects into standardized format"""
        processed = []
        cutoff = datetime.now() - timedelta(hours=self.TIME_WINDOW_HOURS)
        
        for tweet in tweets or []:
            try:
                # Extract timestamp
                timestamp = tweet.created_at if hasattr(tweet, 'created_at') else datetime.now()
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                
                # Filter by time window
                if timestamp < cutoff:
                    continue
                
                # Extract content
                content = getattr(tweet, 'full_text', None) or getattr(tweet, 'text', '')
                
                # Extract user info
                username = 'unknown'
                if hasattr(tweet, 'user'):
                    username = getattr(tweet.user, 'screen_name', 'unknown')
                
                # Extract metrics
                likes = getattr(tweet, 'favorite_count', 0) or getattr(tweet, 'like_count', 0) or 0
                retweets = getattr(tweet, 'retweet_count', 0) or 0
                replies = getattr(tweet, 'reply_count', 0) or 0
                
                # Extract hashtags and mentions
                hashtags = re.findall(r'#(\w+)', content, re.IGNORECASE)
                mentions = re.findall(r'@(\w+)', content)
                
                # Generate content hash for deduplication
                content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
                
                processed.append({
                    'username': username,
                    'timestamp': timestamp,
                    'content': content,
                    'likes': likes,
                    'retweets': retweets,
                    'replies': replies,
                    'hashtags': hashtags,
                    'mentions': mentions,
                    'tweet_id': getattr(tweet, 'id', None),
                    'url': f"https://twitter.com/{username}/status/{getattr(tweet, 'id', '')}" if hasattr(tweet, 'id') else None,
                    'content_hash': content_hash,
                })
            except Exception as e:
                logger.debug(f"Error processing tweet: {e}")
                continue
        
        return processed
    
    def _load_cookies_from_settings(self) -> bool:
        """Load cookies directly from settings (ct0, auth_token, or cookie file)"""
        try:
            # Method 1: Load from ct0 and auth_token
            if self.ct0 and self.auth_token:
                self.cookies = {
                    'ct0': self.ct0,
                    'auth_token': self.auth_token,
                }
                # Add other common Twitter cookies
                if self.username:
                    self.cookies['twid'] = f'u={self.username}'
                logger.info("Loaded cookies from ct0 and auth_token")
                return True
            
            # Method 2: Load from cookie file
            if self.cookie_file:
                import json
                with open(self.cookie_file, 'r') as f:
                    cookie_data = json.load(f)
                    if isinstance(cookie_data, dict):
                        self.cookies = cookie_data
                    elif isinstance(cookie_data, list):
                        # Convert list format to dict
                        self.cookies = {c.get('name'): c.get('value') for c in cookie_data if 'name' in c and 'value' in c}
                    logger.info(f"Loaded cookies from file: {self.cookie_file}")
                    return True
            
            # Method 3: Load from JSON string
            if self.cookies_json:
                import json
                cookie_data = json.loads(self.cookies_json)
                if isinstance(cookie_data, dict):
                    self.cookies = cookie_data
                logger.info("Loaded cookies from JSON string")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Failed to load cookies from settings: {e}")
            return False
    
    async def scrape_all_hashtags(self) -> List[Dict]:
        """Scrape all hashtags and return unique tweets"""
        # Try cookie-based auth first (faster and more reliable)
        if self._load_cookies_from_settings():
            logger.info("Using cookie-based authentication (recommended)")
            if self._transfer_cookies_to_twikit():
                logger.info("Cookie authentication successful")
            else:
                logger.warning("Cookie transfer failed, continuing without authentication")
        # Fallback to Selenium login if cookies not available
        elif self.username and self.password:
            logger.info("Attempting Selenium-based login...")
            logger.info("Note: Twitter often detects automation. Consider using cookie-based auth (TWITTER_CT0 and TWITTER_AUTH_TOKEN) instead.")
            if not self._login_with_selenium():
                logger.warning("Selenium login failed. Twitter may have detected automation.")
                logger.warning("To fix: Add TWITTER_CT0 and TWITTER_AUTH_TOKEN to your .env file")
                logger.warning("You can extract these from your browser's cookies when logged into x.com")
            else:
                self._transfer_cookies_to_twikit()
        else:
            logger.warning("No authentication method available. Scraping may be rate-limited.")
        
        # Scrape hashtags
        all_tweets = []
        seen_hashes = set()
        
        for hashtag in self.HASHTAGS:
            try:
                # Try multiple query variations
                queries = [hashtag, f"{hashtag} lang:en", f'"{hashtag}"']
                
                for query in queries:
                    tweets = await self._search_tweets_async(query, count=500)
                    for tweet in tweets:
                        content_hash = tweet.get('content_hash')
                        if content_hash and content_hash not in seen_hashes:
                            seen_hashes.add(content_hash)
                            all_tweets.append(tweet)
                    
                    if len(all_tweets) >= self.MIN_TWEETS:
                        break
                    
                    await asyncio.sleep(1)  # Rate limiting
                
                hashtag_count = len([t for t in all_tweets if hashtag.lower() in t.get('content', '').lower()])
                logger.info(f"Collected {hashtag_count} tweets for {hashtag}")
                
            except Exception as e:
                logger.error(f"Error scraping {hashtag}: {e}")
        
        # Cleanup
        if self.driver:
            self.driver.quit()
        
        logger.info(f"Total unique tweets collected: {len(all_tweets)}")
        return all_tweets
    
    def scrape_all_hashtags_sync(self) -> List[Dict]:
        """Synchronous wrapper"""
        return asyncio.run(self.scrape_all_hashtags())
