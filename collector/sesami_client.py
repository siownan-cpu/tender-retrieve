
import time
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from dateutil import parser
import pytz

def setup_driver(headless=True):
    from selenium.webdriver.chrome.options import Options

    options = Options()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = webdriver.Chrome(options=options)
    return driver

def parse_sesami_date(date_str):
    """
    Parse date string like '31 Dec 2025 12:00' to datetime object.
    Returns timezone-aware datetime (Singapore time).
    """
    if not date_str:
        return None
    try:
        # Sesami format: 31 Dec 2025 12:00
        # dateutil handles this well
        dt = parser.parse(date_str)
        # Assume Singapore time
        sg_tz = pytz.timezone('Asia/Singapore')
        return sg_tz.localize(dt)
    except:
        return None

def fetch_sesami_opportunities(headless=True, date_mode='24h', custom_days=None, start_date=None, end_date=None):
    """
    Fetch opportunities from Sesami.
    
    Args:
        headless (bool): Run browser in headless mode
        date_mode (str): 'today', '24h', '7days', 'custom'
        custom_days (int): Number of days for custom mode
        start_date (str): Optional 'YYYY-MM-DD' start date to override calculation
        end_date (str): Optional 'YYYY-MM-DD' end date
        
    Returns:
        list: List of opportunity dictionaries
    """
    driver = None
    opportunities = []
    
    # Determine date cutoff
    sg_tz = pytz.timezone('Asia/Singapore')
    now = datetime.now(sg_tz)
    cutoff_date = None
    end_date_obj = None
    
    if start_date:
        try:
            cutoff_date = datetime.strptime(start_date, '%Y-%m-%d')
            cutoff_date = sg_tz.localize(cutoff_date)
        except:
            print(f"⚠ Invalid start_date format: {start_date}")
            
    if end_date:
         try:
            # Set to end of day
            ed = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            end_date_obj = sg_tz.localize(ed)
         except:
            print(f"⚠ Invalid end_date format: {end_date}")

    if not cutoff_date:
        if date_mode == 'today':
            cutoff_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_mode == '24h':
            cutoff_date = now - timedelta(hours=24)
        elif date_mode == '7days':
            cutoff_date = now - timedelta(days=7)
        elif date_mode == 'custom' and custom_days:
            cutoff_date = now - timedelta(days=custom_days)
        elif date_mode == 'all':
            cutoff_date = None # No limit
        
    print(f"\nExample Date Cutoff: {cutoff_date}")
    
    try:
        print("🌐 Starting Chrome for Sesami...")
        driver = setup_driver(headless)
        wait = WebDriverWait(driver, 20)
        
        url = "https://sesami.online/bizopps/businessOpportunities.jsp"
        print(f"📡 Loading {url}...")
        driver.get(url)
        
        # 1. Set Show Entries to 100
        try:
            print("⚙ Setting 'Show entries' to 100...")
            # Wait for table
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#rfqTender")))
            
            select_elem = driver.find_element(By.CSS_SELECTOR, "select[name='rfqTender_length']")
            select = Select(select_elem)
            select.select_by_value('100')
            
            # Wait for table update
            time.sleep(3) 
            
        except Exception as e:
            print(f"⚠ Could not set page size to 100: {e}")
            
        # 2. Iterate pages
        page = 1
        stop_fetching = False
        
        while not stop_fetching:
            print(f"📄 Processing Page {page}...")
            
            # Get Rows
            try:
                # Wait for rows
                rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#rfqTender tbody tr")))
            except:
                print("⚠ No rows found or timeout.")
                break
                
            print(f"  Found {len(rows)} rows on page.")
            
            # Extract data
            page_items_extracted = 0
            
            for row in rows:
                try:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) < 8:
                        continue
                        
                    # Columns (0-indexed based on exploration):
                    # 0: Buyer Company -> calling_entity
                    # 1: Ref No -> itq_itt
                    # 2: Doc Type
                    # 3: Description -> title
                    # 4: Starting Date -> published
                    # 5: Closing Date
                    # 6: Submission
                    # 7: Action (Link)
                    
                    calling_entity = cols[0].text.strip()
                    ref_no = cols[1].text.strip()
                    title = cols[3].text.strip()
                    start_date_str = cols[4].text.strip()
                    closing_date_str = cols[5].text.strip()
                    
                    # Parse Date for Filtering
                    pub_dt = parse_sesami_date(start_date_str)
                    
                    # Check filter
                    if pub_dt:
                        # 1. Stop if older than start_date (cutoff)
                        # Relaxing strict break to handle potential sort irregularities
                        if cutoff_date and pub_dt < cutoff_date:
                            # print(f"  Item date {start_date_str} < cutoff {cutoff_date}. Skipping.")
                            # Check if we should stop? For now, let's just skip to be safe against mixed sort.
                            # But if the whole page is old, we should probably stop.
                            # Just continue for now.
                            continue
                            # stop_fetching = True
                            # break
                        
                        # 2. Skip if newer than end_date
                        if end_date_obj and pub_dt > end_date_obj:
                            # Too new, but don't stop filtering
                            continue
                            
                    # Construct Link
                    link = ''
                    try:
                        action_link = cols[7].find_element(By.TAG_NAME, "a")
                        href = action_link.get_attribute("href") # javascript:viewDetail(...)
                        
                        # Extract IDs
                        # javascript:viewDetail('C585268E...','CAG')
                        match = re.search(r"viewDetail\('([^']+)',\s*'([^']+)'\)", href)
                        if match:
                            doc_id = match.group(1)
                            hub_id = match.group(2)
                            # Construct GET link (assuming it works, otherwise just put the detail)
                            # Logic: JSP forms usually map params.
                            link = f"https://sesami.online/bizopps/businessOpportunityView.jsp?documentID={doc_id}&hubID={hub_id}"
                        else:
                            link = href
                    except:
                        pass

                    item = {
                        'title': title,
                        'link': link,
                        'source': 'sesami',
                        # Use parsed datetime for published date to ensure ISO format (YYYY-MM-DD)
                        # This prevents ambiguity (Day/Month swap) downstream.
                        'published': pub_dt.strftime('%Y-%m-%d') if pub_dt else start_date_str,
                        'itq_itt': ref_no,
                        'calling_entity': calling_entity,
                        'closing_date': closing_date_str,
                        'category': 'Sesami Opportunity', # Default category
                        'opportunity_amount': '' # Not in table, maybe in detail? User didn't ask for detail scrape yet.
                    }
                    
                    opportunities.append(item)
                    page_items_extracted += 1
                    
                except Exception as row_err:
                    print(f"  ⚠ Row error: {row_err}")
                    continue
            
            print(f"  + Added {page_items_extracted} items.")
            
            if stop_fetching:
                break
                
            # Check Next Page
            # Selector for enabled next button
            try:
                # Based on DataTables: a.paginate_button.next
                # If class has 'disabled', it's done.
                next_btn = driver.find_element(By.CSS_SELECTOR, "#rfqTender_next")
                if "disabled" in next_btn.get_attribute("class"):
                    print("  Reached last page.")
                    break
                
                print("  ➡ Next Page...")
                next_btn.click()
                time.sleep(2) # Wait for reload
                page += 1
                
                # Safety break for exploration
                if page > 10: 
                    print("  ⚠ Safety limit (10 pages) reached.")
                    break
                    
            except Exception as e:
                print(f"  ⚠ Pagination clean break or error: {e}")
                break
                
    except Exception as e:
        print(f"❌ Sesami fetch error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
            
    return opportunities

if __name__ == "__main__":
    # Test
    items = fetch_sesami_opportunities(headless=False, date_mode='all')
    print(f"\nExtracted {len(items)} items.")
    if items:
        print(items[0])
