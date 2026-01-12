import time
import re
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

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

class TenderBoardClient:
    def __init__(self):
        self.base_url = "https://www.tenderboard.biz/singaporetenders"
        self.driver = None

    def fetch_opportunities(self, start_date=None, end_date=None):
        """
        Fetches all open procurement opportunities from TenderBoard.
        Returns a list of dicts.
        """
        items = []
        self.driver = setup_driver(headless=True)
        
        try:
            print(f"TenderBoardClient: Navigating to {self.base_url}")
            if start_date:
                print(f"TenderBoardClient: Filter active ({start_date.date()} - {end_date.date() if end_date else 'Now'})")

            self.driver.get(self.base_url)
            
            # Wait for content
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.OpenDeals-resultWrapper-1188477338"))
                )
            except:
                print(f"TenderBoardClient: Timeout waiting for wrapper, proceeding anyway...")

            time.sleep(5) # Wait for JS rendering
            
            page = 1
            max_pages = 20 # Safety limit
            
            while page <= max_pages:
                print(f"TenderBoardClient: Processing Page {page}")
                
                # Re-fetch elements on each iteration to avoid stale elements
                links = self.driver.find_elements(By.CSS_SELECTOR, "a[class*='OpenDeals-viewLink']")
                print(f"TenderBoardClient: Found {len(links)} items on page {page}")
                
                if not links and page == 1:
                     print("Retrying wait for content...")
                     time.sleep(5)
                     links = self.driver.find_elements(By.CSS_SELECTOR, "a[class*='OpenDeals-viewLink']")
                
                for link_elem in links:
                    try:
                        title = link_elem.text.strip()
                        if not title:
                            continue
                            
                        # Find row container (ancestor mdl-grid)
                        try:
                            row = link_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'mdl-grid')]")
                        except Exception:
                            # print("Could not find ancestor row")
                            continue
                        
                        # Extract Data
                        
                        # 1. Buyer Name & Industry
                        buyer_name = "TenderBoard (Unknown Buyer)"
                        industry_val = "General"
                        
                        try:
                            # Robust Extraction strategies
                            full_row_text = row.text
                            
                            # Strategy A: Industry from text
                            # "Industry: Construction: General Building..."
                            m_ind = re.search(r'Industry:\s*(.+?)(?:\n|$)', full_row_text)
                            if m_ind:
                                industry_val = m_ind.group(1).strip()
                            
                            # Strategy B: Buyer from Logo Image (Best for reliability)
                            # Screenshot shows logos: SAFRA, UWC, APSN
                            try:
                                logo = row.find_element(By.CSS_SELECTOR, "img.agency-logo, div.agency-logo img, img[alt]")
                                alt_text = logo.get_attribute('alt') or logo.get_attribute('title')
                                if alt_text and len(alt_text) > 2 and "logo" not in alt_text.lower():
                                    buyer_name = alt_text.strip()
                            except:
                                pass
                                
                            # Strategy C: Buyer from Text (Fallback)
                            if "Unknown Buyer" in buyer_name:
                                # Split text, filter out title, industry, dates
                                lines = [xx.strip() for xx in full_row_text.split('\n') if xx.strip()]
                                candidates = []
                                for l in lines:
                                    if l == title: continue
                                    if "Industry:" in l: continue
                                    if "Published" in l: continue
                                    if "Closes" in l: continue
                                    if len(l) < 3: continue
                                    # Heuristic: Buyer is usually a standalone line, often uppercase or Proper Case
                                    candidates.append(l)
                                
                                if candidates:
                                    # Pick the one that looks most like an org (not a date, not a status)
                                    for c in candidates:
                                         if not any(char.isdigit() for char in c) and "EXCLUSIVE" not in c:
                                             buyer_name = c
                                             break
                        except Exception as e:
                            pass
                            
                        # 1b. Reference Number (Heuristic)
                        # Check candidates for patterns like "TO/..." (SIT) or "Ref:..."
                        ref_no = None
                        try:
                            for c in candidates:
                                if c.startswith("TO") or c.startswith("PT") or "Ref No" in c:
                                    # Ensure it has digits (to avoid noise)
                                    if any(char.isdigit() for char in c):
                                        ref_no = c.replace('Ref No:', '').strip()
                                        break
                        except:
                            pass
                        
                        # 2. Dates
                        pub_date_str = ""
                        closing_date_str = ""
                        pub_dt_obj = None # To store datetime for filtering
                        
                        # Fix: Ensure cells is defined in this scope
                        cells = row.find_elements(By.CSS_SELECTOR, "div.mdl-cell")
                        for cell in cells:
                            raw_txt = cell.text.strip()
                            flat_txt = raw_txt.replace('\n', ' ').replace('\r', ' ')
                            # Skip long text cells (Description) to avoid false positives
                            if len(flat_txt) > 100:
                                continue
                                
                            # Regex split for date range
                            parts = re.split(r'\s*[-–]\s*', flat_txt)
                            
                            # Fallback: Find all dates in text (only if short text)
                            date_matches = []
                            matches = re.findall(r'(\d{1,2}[-/\s]+[A-Za-z]{3}(?:[-/\s]+\d{2,4})?)', flat_txt)
                            if matches:
                                date_matches = matches
                            
                            is_date_row = False
                            
                            # Case 1: Standard Range (Start - End)
                            if len(parts) >= 2:
                                 # strict check: must start with digit
                                 if (re.search(r'^\d', parts[0]) and re.search(r'\d', parts[1])):
                                     start_raw = parts[0].strip()
                                     end_raw = parts[1].strip()
                                     is_date_row = True
                            
                            # Case 2: Regex found 2 dates (e.g. no hyphen or different separator)
                            elif len(date_matches) >= 2:
                                start_raw = date_matches[0]
                                end_raw = date_matches[-1]
                                is_date_row = True
                            
                            if is_date_row:
                                     # Parse Start (Published Date) - assume past/recent
                                     # Heuristic: Pub date shouldn't be far in future. 
                                     # If today is Jan 2024, "Dec 25" means Dec 2023.
                                     start_dt = self._parse_smart_date(start_raw, is_closing=False)
                                     
                                     if start_dt:
                                         pub_date_str = start_dt.strftime("%d %b %Y")
                                         pub_dt_obj = start_dt
                                         
                                         # Parse End (Closing Date) - use start_dt as reference
                                         # If start is Dec 2023, and end is "Jan 5", it usually means Jan 2024.
                                         end_dt = self._parse_smart_date(end_raw, is_closing=True, ref_start_date=start_dt)
                                         
                                         if end_dt:
                                             closing_date_str = end_dt.strftime("%d %b %Y")
                                             
                                         # We found our dates, stop checking other cells
                                         break
                        
                        # DATE FILTER CHECK
                        if start_date and pub_dt_obj:
                             # Check if published date is within range
                             # Compare dates only
                             if pub_dt_obj.date() < start_date.date():
                                 # Too old
                                 continue
                             if end_date and pub_dt_obj.date() > end_date.date():
                                 # Start date is in future (beyond range)? Unlikely for "Last Working Day" but possible.
                                 continue
                        elif start_date and not pub_dt_obj:
                             # If we have a filter but failed to parse date, safer to Include it?
                             # Or Exclude?
                             # Usually better to Include if unsure to avoid missing data, but user wants strict filtering.
                             # Let's Exclude if parsing totally failed? No, might miss valid items with weird date formats.
                             # Revert: Include if date missing.
                             pass

                        # 3. Link
                        link = link_elem.get_attribute('href')
                        if not link or "javascript" in link:
                             # Try to find any other link in the row
                             try:
                                 all_row_links = row.find_elements(By.TAG_NAME, "a")
                                 for al in all_row_links:
                                     h = al.get_attribute('href')
                                     if h and "javascript" not in h and "tenderboard.biz" in h:
                                         link = h
                                         break
                             except:
                                 pass
                        
                        if not link or "javascript" in link:
                             print(f"Warning: No valid link found for {title}")
                             link = self.base_url

                        items.append({
                            'title': title,
                            'link': link,
                            'buyer': buyer_name,
                            'industry': industry_val,
                            'pub_date': pub_date_str,
                            'close_date': closing_date_str,
                            'ref_no': ref_no,
                            'source': 'TenderBoard'
                        })
                        
                    except Exception as e:
                        print(f"Error parsing item: {e}")
                        continue
                
                # Pagination Logic
                try:
                    next_btns = self.driver.find_elements(By.CSS_SELECTOR, "li.btn-next-page")
                    if not next_btns:
                        print("No next button found.")
                        break
                    
                    next_btn = next_btns[0]
                    if "disabled" in next_btn.get_attribute("class"):
                        print("Reached last page (disabled Next button).")
                        break
                    
                    # Click Next
                    print(f"Clicking Next page...")
                    next_btn.find_element(By.TAG_NAME, "a").click()
                    page += 1
                    time.sleep(5) # Wait for load
                    
                except Exception as e:
                    print(f"Pagination error: {e}")
                    break
                    
        except Exception as e:
            print(f"TenderBoardClient: Fetch error: {e}")
        finally:
            if self.driver:
                self.driver.quit()
        
        return items

    def _parse_smart_date(self, date_str, is_closing=False, ref_start_date=None):
        """
        Parses date string with support for 'DD MMM' (missing year).
        is_closing: If True, biased towards future dates.
        ref_start_date: If provided (for closing date), helps infer year relative to start.
        """
        if not date_str:
            return None
            
        # Clean string
        date_str = date_str.strip()
        
        # 1. Try Full Formats (Year explicit)
        full_formats = [
            "%d %b %y", # 9 Sep 25
            "%d %b %Y", # 9 Sep 2025
            "%d-%b-%Y", # 9-Sep-2025
            "%d/%m/%Y", # 09/01/2025
            "%Y-%m-%d", # 2025-01-09
        ]
        
        for fmt in full_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # Sanity check year (e.g. 2-digit year)
                if dt.year < 2000:
                    dt = dt.replace(year=dt.year + 2000) # Fix 2-digit year if parsed as 19xx
                return dt
            except:
                continue
                
        # 2. Try Partial Format (DD MMM)
        try:
             # Extract strictly DD MMM pattern to avoid garbage
             # pattern: start of string or space, 1-2 digits, space, 3 letters
             match = re.search(r'\b(\d{1,2})\s+([A-Za-z]{3})\b', date_str)
             if match:
                 clean_str = f"{match.group(1)} {match.group(2)}"
                 dt = datetime.strptime(clean_str, "%d %b") # Year 1900
                 
                 now = datetime.now()
                 if ref_start_date:
                     # If we have a reference start date, use its year baseline
                     year = ref_start_date.year
                     dt = dt.replace(year=year)
                     
                     # If closing date is earlier than start date, it must be next year
                     # e.g. Start: Dec 2023, End: Jan (becomes Jan 2023 < Dec 2023) -> Jan 2024
                     if dt < ref_start_date:
                         dt = dt.replace(year=year + 1)
                 else:
                     # No reference, use Current Date baseline
                     year = now.year
                     dt = dt.replace(year=year)
                     
                     if not is_closing:
                         # Published Date Logic: Biased to Past
                         # If date is in future by > 3 months? imply last year?
                         # e.g. Today Jan 2024. Date "Dec 15" -> Dec 15 2024 (Future) -> Infer Dec 2023.
                         if dt > now + list(map(lambda x: x, [timedelta(days=7)]))[0]: # small future buffer
                              dt = dt.replace(year=year - 1)
                     else:
                         # Closing Date Logic: Biased to Future
                         # If date is in past by > 3 months? imply next year?
                         # e.g. Today Dec 2023. Date "Jan 15" -> Jan 15 2023 (Past) -> Infer Jan 2024?
                         # Usually closing date > today.
                         if dt < now - timedelta(days=90):
                              dt = dt.replace(year=year + 1)
                              
                 return dt
        except Exception as e:
             # print(e)
             pass

        return None

if __name__ == "__main__":
    client = TenderBoardClient()
    results = client.fetch_opportunities()
    print(f"Total Found {len(results)} items.")
    # Print first few to verify
    for r in results[:5]:
        print(f"[{r['buyer']}] {r['title']} ({r['pub_date']} - {r['close_date']})")
