
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

def get_chrome_driver(headless=True):
    """
    Returns a configured Chrome WebDriver instance.
    Respects CHROME_BIN and CHROMEDRIVER_PATH environment variables.
    """
    options = Options()
    
    # Binary Location (Critical for Chromium on Render)
    chrome_bin = os.environ.get('CHROME_BIN')
    if chrome_bin:
        options.binary_location = chrome_bin

    if headless:
        options.add_argument('--headless=new')
    
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage') # Critical for Docker shared memory limits
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Suppress logging
    options.add_argument('--log-level=3')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    # Service with Executable Path
    chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
    service = None
    if chromedriver_path:
        service = Service(executable_path=chromedriver_path)
    
    try:
        if service:
            return webdriver.Chrome(service=service, options=options)
        else:
            return webdriver.Chrome(options=options)
    except Exception as e:
        print(f"Error initializing Chrome Driver in util/driver_setup: {e}")
        # Fallback: Try without service if specific path failed? 
        # Or usually it implies path is wrong. Rethrow.
        raise e
