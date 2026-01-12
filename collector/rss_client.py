import feedparser
import yaml
import requests
import time
from pathlib import Path
from datetime import datetime
from functools import lru_cache

@lru_cache(maxsize=1)
def load_feeds_config():
    """Load RSS feed configuration from YAML file"""
    cfg = Path('config/feeds.yaml')
    if not cfg.exists():
        print("WARNING: config/feeds.yaml not found!")
        return {}
    data = yaml.safe_load(cfg.read_text()) or {}
    return data.get('feeds', {})

def fetch_single_feed(url, headers, timeout=15, max_retries=3):
    """
    Fetch a single RSS feed with retry logic
    
    Args:
        url: RSS feed URL
        headers: HTTP headers
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        
    Returns:
        tuple: (success, items, error_message)
    """
    items = []
    
    for attempt in range(max_retries):
        try:
            print(f"  Fetching: {url}")
            print(f"    Attempt {attempt + 1}/{max_retries}...")
            
            # Fetch with requests
            resp = requests.get(url, headers=headers, timeout=timeout)
            
            print(f"    HTTP Status: {resp.status_code}")
            
            if resp.status_code != 200:
                if attempt < max_retries - 1:
                    print(f"    Non-200 status, retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                else:
                    return False, [], f"HTTP {resp.status_code}"
            
            # Check content type
            content_type = resp.headers.get('Content-Type', '')
            print(f"    Content-Type: {content_type}")
            
            # Parse RSS/XML
            feed = feedparser.parse(resp.text)
            
            # Check for parsing errors
            if hasattr(feed, 'bozo') and feed.bozo:
                bozo_exception = getattr(feed, 'bozo_exception', 'Unknown parsing error')
                print(f"    WARNING: Feed parsing issue: {bozo_exception}")
                # Continue anyway, some feeds work despite bozo flag
            
            # Check if feed has entries
            if not feed.entries:
                print(f"    WARNING: Feed has 0 entries")
                # Check if it's actually XML/RSS
                if 'xml' not in content_type.lower() and 'rss' not in content_type.lower():
                    return False, [], f"Not XML/RSS content (got: {content_type})"
                # Empty feed is not an error, just no items
                return True, [], None
            
            print(f"    ✓ Found {len(feed.entries)} entries")
            
            # Extract items
            for e in feed.entries:
                # Try multiple date fields from RSS
                published = (
                    e.get('published', '') or 
                    e.get('updated', '') or 
                    e.get('pubDate', '') or
                    e.get('date', '')
                )
                
                # If no string date, try parsed date
                if not published and hasattr(e, 'published_parsed') and e.published_parsed:
                    try:
                        published = time.strftime('%Y-%m-%d %H:%M:%S', e.published_parsed)
                    except:
                        pass
                
                if not published and hasattr(e, 'updated_parsed') and e.updated_parsed:
                    try:
                        published = time.strftime('%Y-%m-%d %H:%M:%S', e.updated_parsed)
                    except:
                        pass
                
                # GeBIZ-specific: Extract date from summary if no RSS date found
                if not published:
                    summary = e.get('summary', '') or e.get('description', '')
                    if summary and 'Published Date' in summary:
                        # Extract "Published Date: DD/MM/YYYY" (GeBIZ format)
                        import re
                        match = re.search(r'Published Date:\s*(\d{1,2}/\d{1,2}/\d{4})', summary)
                        if match:
                            date_str = match.group(1)
                            # Fix GeBIZ Glitch: Detect future year (e.g. 2026 when it's 2025/2026 transition and tenders act weird)
                            # Logic: If date is > 180 days in future, assume it's last year
                            try: 
                                from datetime import datetime, timedelta
                                dt = datetime.strptime(date_str, "%d/%m/%Y")
                                now = datetime.now()
                                if dt > now + timedelta(days=180):
                                    # Subtract 1 year
                                    dt = dt.replace(year=dt.year - 1)
                                    date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                                else:
                                    # Convert to standard format for consistency
                                    date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                                published = date_str
                            except:
                                published = match.group(1)
                
                # Determine if this is an Award feed
                is_award = ('_AWD_FEED' in url or '-CREATE_AWD_FEED' in url)

                item = {
                    'source': 'rss',
                    'title': e.get('title', ''),
                    'link': e.get('link', ''),
                    'summary': e.get('summary', '') or e.get('description', '') or e.get('content', [{'value': ''}])[0].get('value', ''),
                    'published': published,
                    'feed_url': url,
                    '_is_award': is_award
                }
                items.append(item)
            
            return True, items, None
            
        except requests.exceptions.Timeout:
            error = f"Timeout after {timeout}s"
            print(f"    ERROR: {error}")
            if attempt < max_retries - 1:
                print(f"    Retrying in 3 seconds...")
                time.sleep(3)
                continue
            return False, [], error
            
        except requests.exceptions.ConnectionError as e:
            error = f"Connection error: {str(e)[:100]}"
            print(f"    ERROR: {error}")
            if attempt < max_retries - 1:
                print(f"    Retrying in 3 seconds...")
                time.sleep(3)
                continue
            return False, [], error
            
        except requests.exceptions.RequestException as e:
            error = f"Request error: {str(e)[:100]}"
            print(f"    ERROR: {error}")
            if attempt < max_retries - 1:
                print(f"    Retrying in 3 seconds...")
                time.sleep(3)
                continue
            return False, [], error
            
        except Exception as e:
            error = f"Unexpected error: {str(e)[:100]}"
            print(f"    ERROR: {error}")
            if attempt < max_retries - 1:
                print(f"    Retrying in 3 seconds...")
                time.sleep(3)
                continue
            return False, [], error
    
    return False, [], "Max retries exceeded"

def fetch_feeds(selected_urls=None, all_feeds=False, date_mode='today', start_date=None, end_date=None):
    """
    Fetch items from RSS feeds with detailed logging and date filtering
    
    Args:
        selected_urls: List of specific URLs to fetch
        all_feeds: If True, fetch all configured feeds
        date_mode: 'today', 'last_7_days', 'last_24_hours', 'custom', 'specific_date', 'all'
        start_date: Start date for custom/specific_date mode (YYYY-MM-DD)
        end_date: End date for custom mode (YYYY-MM-DD)
        
    Returns:
        list: List of feed items (filtered by date if date_mode != 'all')
    """
    from dateutil import parser as date_parser
    import pytz
    from datetime import timedelta
    
    print("\n" + "="*80)
    print("RSS FEED FETCHING STARTED (GeBIZ)")
    print("="*80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Date Mode: {date_mode}")
    if start_date or end_date:
        print(f"Date Range: {start_date or 'N/A'} to {end_date or 'N/A'}")
    
    # Collect URLs to fetch
    feed_urls = set()
    
    if selected_urls:
        feed_urls.update(selected_urls)
        print(f"Mode: Selected feeds ({len(feed_urls)} URLs)")
    
    if all_feeds or (not selected_urls):
        if all_feeds:
            feeds = load_feeds_config()
            for main, subs in feeds.items():
                for sub, types in subs.items():
                    for url in types.values():
                        feed_urls.add(url)
            print(f"Mode: All feeds ({len(feed_urls)} URLs)")
    
    if not feed_urls:
        print("WARNING: No feed URLs to fetch!")
        print("="*80 + "\n")
        return []
    
    print(f"Total feeds to fetch: {len(feed_urls)}")
    print("="*80 + "\n")
    
    # HTTP headers
    # HTTP headers (Mimic Chrome to avoid blocking)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    # Fetch each feed
    all_items = []
    success_count = 0
    fail_count = 0
    empty_count = 0
    
    for idx, url in enumerate(feed_urls, 1):
        print(f"\n[{idx}/{len(feed_urls)}] Processing feed:")
        
        success, items, error = fetch_single_feed(url, headers)
        
        if success:
            if items:
                all_items.extend(items)
                success_count += 1
                print(f"  ✓ SUCCESS: Added {len(items)} items")
            else:
                empty_count += 1
                print(f"  ⚠ EMPTY: Feed has no entries")
        else:
            fail_count += 1
            print(f"  ✗ FAILED: {error}")
        
        # Small delay between requests to be polite
        if idx < len(feed_urls):
            time.sleep(0.5)
    
    # Summary
    print("\n" + "="*80)
    print("FETCH SUMMARY")
    print("="*80)
    print(f"Total feeds attempted: {len(feed_urls)}")
    print(f"✓ Successful with items: {success_count}")
    print(f"⚠ Empty feeds: {empty_count}")
    print(f"✗ Failed: {fail_count}")
    print(f"📊 Total items retrieved: {len(all_items)}")
    print("="*80 + "\n")
    
    # Apply date filtering if not 'all' mode
    if date_mode != 'all' and all_items:
        print("📅 Applying GeBIZ date filter...")
        
        sg_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(sg_tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate cutoff date
        cutoff_date = None
        end_date_obj = None
        
        if start_date:
            try:
                cutoff_date = datetime.strptime(start_date, '%Y-%m-%d')
                cutoff_date = sg_tz.localize(cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0))
            except:
                print(f"⚠ Invalid start_date: {start_date}")
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                end_date_obj = sg_tz.localize(end_date_obj.replace(hour=23, minute=59, second=59, microsecond=999999))
            except:
                print(f"⚠ Invalid end_date: {end_date}")
        
        if not cutoff_date:
            if date_mode == 'today':
                cutoff_date = today_start
            elif date_mode == 'last_24_hours':
                cutoff_date = now - timedelta(hours=24)
            elif date_mode == 'last_7_days':
                cutoff_date = today_start - timedelta(days=6)
            elif date_mode == 'last_14_days':
                cutoff_date = today_start - timedelta(days=13)
            elif date_mode == 'last_31_days':
                cutoff_date = today_start - timedelta(days=30)
            elif date_mode == 'last_90_days':
                cutoff_date = today_start - timedelta(days=89)
            elif date_mode == 'last_365_days':
                cutoff_date = today_start - timedelta(days=364)
            elif date_mode in ['custom', 'specific_date']:
                cutoff_date = today_start  # Default to today if no start_date
        
        print(f"   Cutoff: {cutoff_date}")
        if end_date_obj:
            print(f"   End: {end_date_obj}")
        
        # Filter items
        filtered_items = []
        items_no_date = 0
        items_out_of_range = 0
        
        for item in all_items:
            pub_str = item.get('published', '')
            
            if not pub_str:
                items_no_date += 1
                continue
            
            # Parse date
            try:
                pub_dt = date_parser.parse(pub_str)
                if pub_dt.tzinfo is None:
                    pub_dt = sg_tz.localize(pub_dt)
                else:
                    pub_dt = pub_dt.astimezone(sg_tz)
                
                # Check date range
                if cutoff_date and pub_dt < cutoff_date:
                    items_out_of_range += 1
                    continue
                
                if end_date_obj and pub_dt > end_date_obj:
                    items_out_of_range += 1
                    continue
                
                filtered_items.append(item)
                
            except:
                items_no_date += 1
                continue
        
        print(f"   ✓ Items in range: {len(filtered_items)}")
        print(f"   ⏭ Items without date: {items_no_date}")
        print(f"   ⏭ Items out of range: {items_out_of_range}")
        print(f"   📊 Filter result: {len(filtered_items)}/{len(all_items)} items")
        
        all_items = filtered_items
    
    if fail_count > 0:
        print("⚠ TROUBLESHOOTING TIPS:")
        print("  1. Check internet connection")
        print("  2. Verify GeBIZ website is accessible: https://www.gebiz.gov.sg")
        print("  3. Check if corporate firewall/proxy is blocking RSS feeds")
        print("  4. Try accessing an RSS feed directly in browser")
        print("  5. Check if feeds have been recently updated by GeBIZ")
        print("="*80 + "\n")
    
    if len(all_items) == 0 and success_count == 0:
        print("❌ NO ITEMS RETRIEVED!")
        print("   Possible reasons:")
        print("   - Network/firewall blocking access to www.gebiz.gov.sg")
        print("   - All selected feeds are currently empty")
        print("   - GeBIZ RSS service may be temporarily unavailable")
        print("="*80 + "\n")
    
    return all_items
