
import time
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium import webdriver

def setup_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = webdriver.Chrome(options=options)
    return driver

class JPMCClient:
    def __init__(self):
        self.base_url = "https://jpmcbrunei.com/tender-quotation/"
        self.driver = None

    def fetch_opportunities(self, date_mode='all', start_date=None, end_date=None):
        """
        Fetches procurement opportunities from JPMC Brunei.
        Returns a list of dicts.
        """
        items = []
        self.driver = setup_driver(headless=True)
        
        try:
            print(f"JPMCClient: Navigating to {self.base_url}")
            if start_date:
                print(f"JPMCClient: Filter mode {date_mode} ({start_date.date()} to {end_date.date() if end_date else 'Now'})")

            self.driver.get(self.base_url)
            
            # Wait for grid items to load
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "jet-listing-grid__item"))
            )
            
            # Find all grid items (rows)
            grid_items = self.driver.find_elements(By.CLASS_NAME, "jet-listing-grid__item")
            print(f"JPMCClient: Found {len(grid_items)} items")
            
            for item_div in grid_items:
                try:
                    # Find all columns content within this item
                    cols = item_div.find_elements(By.CLASS_NAME, "jet-listing-dynamic-field__content")
                    
                    if len(cols) < 6:
                        continue
                        
                    # Indices based on analysis:
                    # 0: Index (1, 2, 3...)
                    # 1: Ref No (JPMC/PD/TEN/...)
                    # 2: Title (Description)
                    # 3: N/A
                    # 4: Fee
                    # 5: Closing Date
                    
                    ref_no = cols[1].text.strip()
                    title_text = cols[2].text.strip()
                    closing_raw = cols[5].text.strip()
                    closing_str = closing_raw.replace('@', '').strip()
                    
                    # Clean title (remove newlines if excessive)
                    title = title_text.replace('\n', ' ').strip()

                    # Extract "Last Date For Tender Purchase"
                    last_date_str = ""
                    if "Last Date For Tender Purchase:" in title_text:
                        try:
                            # Split by label
                            parts = title_text.split("Last Date For Tender Purchase:")
                            if len(parts) > 1:
                                sub = parts[1].strip()
                                import re
                                date_match = re.search(r'(\d{1,2})(?:ST|ND|RD|TH)?\s+([A-Z]+)\s+(\d{4})', sub, re.IGNORECASE)
                                if date_match:
                                    day = date_match.group(1)
                                    month = date_match.group(2)
                                    year = date_match.group(3)
                                    clean_date_str = f"{day} {month} {year}"
                                    
                                    # Parse
                                    last_purchase_dt = datetime.strptime(clean_date_str, "%d %B %Y")
                                    
                                    # Filter Logic:
                                    # 1. Active (Future/Today): Keep
                                    # 2. Expired (Past): Keep ONLY if within filter range
                                    
                                    is_expired = last_purchase_dt.date() < datetime.now().date()
                                    
                                    if is_expired:
                                        # It is expired. Check if user wants to see it based on date filter.
                                        keep_expired = False
                                        if start_date:
                                            # Check if the purchase date falls within the selected range
                                            # e.g. "Last 7 Days". If purchase date is yesterday, it is in range.
                                            item_date = last_purchase_dt.date()
                                            filter_start = start_date.date()
                                            filter_end = end_date.date() if end_date else datetime.now().date()
                                            
                                            if filter_start <= item_date <= filter_end:
                                                keep_expired = True
                                        
                                        if not keep_expired:
                                            # print(f"  Skipping expired item: {title[:30]}... ({last_purchase_dt.date()})")
                                            continue
                        except Exception as e:
                            pass
                        except Exception as e:
                            # print(f"Error parsing Last Tender Date: {e}")
                            pass
                            
                    # Additional check on Closing Date if available
                    if closing_str:
                         try:
                             # Expected format: "12 Dec 2026 12:00PM" or similar?
                             # Actually usually just date. Let's try flexible parse.
                             pass # Todo: implement strict closing date check if needed
                         except:
                             pass

                    items.append({
                        "title": title, # Use raw title (without ref no prefix, as ref_no is separate)
                        "ref_no": ref_no, # Explicit Ref No
                        "link": self.base_url,
                        "pub_date": last_purchase_dt.strftime('%d %b %Y') if 'last_purchase_dt' in locals() else "", 
                        "closing_date": closing_str,
                        "source": "JPMC Brunei"
                    })
                    
                    # Cleanup for next iteration
                    if 'last_purchase_dt' in locals(): del last_purchase_dt
                    
                except Exception as e:
                    print(f"JPMCClient: Error parsing item: {e}")
                    continue

        except Exception as e:
            print(f"JPMCClient: Fetch error: {e}")
        finally:
            if self.driver:
                self.driver.quit()
        
        return items

if __name__ == "__main__":
    client = JPMCClient()
    results = client.fetch_opportunities()
    print(f"Found {len(results)} items:")
    for r in results:
        print(r)
