
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from util.driver_setup import get_chrome_driver



class AribaScraper:
    def __init__(self, headless=True):
        self.driver = get_chrome_driver(headless)
        self.wait = WebDriverWait(self.driver, 15)
        self.base_url = 'https://portal.us.bn.cloud.ariba.com/dashboard/public/appext/comsapsbncdiscoveryui#/leads/search?anId=ANONYMOUS'

    def close(self):
        if self.driver:
            self.driver.quit()

    def nav_to_search(self):
        print(f"[Nav] Going to {self.base_url}")
        self.driver.get(self.base_url)
        time.sleep(8) # Initial load wait
        
        # Check login/landing
        self.check_for_login()

    def search_keyword(self, keyword="Singapore"):
        print(f"[Search] Keyword: {keyword}")
        try:
            # Check if search is already applied e.g. via URL or stored state?
            # Ariba often clears state on refresh, so we usually need to re-type.
            
            # Find input
            search_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='Search']")))
            
            # Check current value
            curr = search_input.get_attribute("value")
            if curr and keyword.lower() in curr.lower():
                print("  Keyword already present.")
                return

            search_input.clear()
            search_input.send_keys(keyword)
            time.sleep(1)
            search_input.send_keys(Keys.ENTER)
            
            print("  Submitted. Waiting for update...")
            time.sleep(6) # Wait for results
            
        except Exception as e:
            print(f"  [!] Search error: {e}")

    def sort_results(self, sort_option="Newest Leads"):
        print(f"[Sort] Applying sort: {sort_option}...")
        try:
            # 1. Try finding 'Sort By' label
            dropdown = None
            try:
                # Look for label text 'Sort By'
                labels = self.driver.find_elements(By.XPATH, "//label[contains(text(), 'Sort By')]")
                for lbl in labels:
                    if lbl.is_displayed():
                        # Dropdown is usually the next sibling div or inside a container
                        # SAP UI5 often has Label then Div
                        possible_dd = lbl.find_element(By.XPATH, "./following::div[contains(@class,'sapMSlt')][1]")
                        if possible_dd.is_displayed():
                            dropdown = possible_dd
                            break
            except:
                pass

            # 2. Fallback: Look for dropdown containing 'Relevance' or 'Date Posted' (if not filter)
            if not dropdown:
                # Common default is Relevance
                candidates = self.driver.find_elements(By.XPATH, "//div[contains(@class,'sapMSlt')]")
                for cand in candidates:
                    text = cand.text
                    if "Relevance" in text or "Newest Leads" in text or "Closing Soonest" in text:
                        if cand.is_displayed():
                            dropdown = cand
                            break

            if dropdown:
                # Click dropdown
                # Use JS click if standard click fails
                try:
                    dropdown.click()
                except:
                    self.driver.execute_script("arguments[0].click();", dropdown)
                
                time.sleep(1.5)
                
                # Find option
                option_xpath = f"//li[contains(text(), '{sort_option}')] | //div[contains(text(), '{sort_option}')]"
                options = self.driver.find_elements(By.XPATH, option_xpath)
                target_opt = None
                for opt in options:
                    if opt.is_displayed():
                        target_opt = opt
                        break
                
                if target_opt:
                    target_opt.click()
                    print(f"  ✓ Selected '{sort_option}'")
                    time.sleep(5) # Wait for re-sort
                else:
                    print(f"  [!] Option '{sort_option}' not found in dropdown.")
                    # Close dropdown
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            else:
                 print("  [!] Sort dropdown not found.")

        except Exception as e:
            print(f"  [!] Sort error: {e}")

    def apply_date_filter(self, mode='today', days=None):
        print(f"[Filter] Mode: {mode}, Days: {days}")
        
        # Default
        target = "Last 24 hours"
        
        # Mapping Logic
        if mode == 'last_working_day':
            # Map Last Working Day -> Last 7 Days (Ariba doesn't have working day logic)
            target = "Last 7 days"
        
        elif mode == 'last_7_days' or (days is not None and days <= 7 and days > 1): 
            target = "Last 7 days"
        elif mode == 'last_14_days' or (days is not None and days <= 14 and days > 7): 
            target = "Last 14 days"
        elif mode == 'last_31_days' or (days is not None and days <= 31 and days > 14): 
            target = "Last 31 days"
        elif mode == 'last_90_days' or (days is not None and days <= 90 and days > 31):
            target = "Last 90 days"
        elif mode == 'last_365_days' or (days is not None and days > 90):
            target = "Last 365 days"
            
        # Fallback for custom without days or specific mappings
        if target == "Last 24 hours" and mode not in ['today', 'last_24_hours']:
             if mode == 'custom' or mode == 'specific_date':
                 # If days wasn't calculated for some reason, default to 365 to be safe
                 if days is None: target = "Last 365 days"
                 # Else it was handled by the numeric checks above

            
        print(f"[Filter] Mapped mode '{mode}' to Ariba option '{target}'")

        try:
             # Find "Date Posted" dropdown with Retry
            dd = None
            for attempt in range(3):
                # Locate by label near it
                try:
                    # Use strict XPath based on prev debug
                    dd = self.driver.find_element(By.XPATH, "//label[contains(., 'Date Posted')]/following::div[contains(@class, 'sapMSlt')][1]")
                    if dd.is_displayed():
                        break
                except:
                    pass
                time.sleep(1)
            
            if dd:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dd)
                try:
                    dd.click()
                except:
                    self.driver.execute_script("arguments[0].click();", dd)
                
                time.sleep(1.5)
                
                # Select option
                opts = self.driver.find_elements(By.XPATH, f"//li[contains(text(), '{target}')]")
                clicked = False
                for o in opts:
                    if o.is_displayed():
                        o.click()
                        clicked = True
                        break
                
                if clicked:
                    print(f"  ✓ Applied {target}")
                    time.sleep(5)
                else:
                    print(f"  [!] Option {target} not hidden/found")
            else:
                print("  [!] Date filter dropdown not found")
                
        except Exception as e:
            print(f"  [!] Filter error: {e}")

    def _scrape_current_page(self):
        items = []
        try:
            print("[Extract] finding items...")
            # Wait for items to be present
            try:
                self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".sapMLIB")))
            except:
                print("  [!] Timed out waiting for items")
                return []

            # Selectors
            item_selector = ".sapMLIB"
            rows = self.driver.find_elements(By.CSS_SELECTOR, item_selector)
            
            print(f"  Found {len(rows)} items")
            if not rows:
                return []

            main_handle = self.driver.current_window_handle
            
            for i in range(len(rows)):
                if i >= 50: break # Safety limit
                
                # Re-find row/items to avoid stale element (the DOM might change if we interact or if things load)
                try:
                    current_rows = self.driver.find_elements(By.CSS_SELECTOR, item_selector)
                    if i < len(current_rows):
                        row = current_rows[i]
                    else:
                        break
                except:
                    continue

                item_data = {
                    'title': 'N/A',
                    'link': self.base_url,
                    'summary': '',
                    'published': '',
                    'source': 'ariba'
                }

                try:
                    # Scroll into view
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
                    time.sleep(0.2)

                    # Strict Selector: Title MUST be inside the Identifier Title container
                    # This avoids picking up RFI IDs which are also `sapMLnk`
                    try:
                        title_el = row.find_element(By.CSS_SELECTOR, ".sapMObjectIdentifierTitle .sapMLnk")
                    except:
                        # Fallback: Try `a` with id containing `title`
                        title_el = row.find_element(By.CSS_SELECTOR, "a[id*='title']")
                    
                    item_data['title'] = title_el.text.strip()
                    
                    if not item_data['title']:
                         # Try getting inner text or title attribute
                         item_data['title'] = title_el.get_attribute("textContent").strip()
                         
                    # Try to extract Category from Row Text (Optimization)
                    row_text = row.text
                    cat_match_row = re.search(r'(?:Product\s+)?Category\s*[:\.\-]\s*([^\n\r]+)', row_text, re.IGNORECASE)
                    if cat_match_row:
                        item_data['category'] = cat_match_row.group(1).strip()
                        
                except Exception as e:
                    # print(f"    ~ Title extract fail: {e}")
                    continue # Skip if no title
                
                if "Mock" in item_data['title']: continue

                print(f"  Processing [{i+1}]: {item_data['title'][:40]}...")

                # 2. Get Details via New Tab Strategy
                try:
                    # Strategy: Open in new tab to preserve main page state (pagination/search)
                    main_window = self.driver.current_window_handle
                    
                    # Method A: Ctrl+Click
                    # Method B: Get href and open window
                    
                    # Ariba titles often don't have hrefs, they are JS buttons.
                    # Ctrl+Click might not work on JS buttons.
                    # If it's an <a> tag with href, good. If not, we might have to click normally.
                    # BUT if it's a JS button, `click` navigates the current page.
                    
                    # CHECK: Is it a link?
                    is_link = False
                    href = title_el.get_attribute('href')
                    if href and 'javascript' not in href and '#' not in href:
                        is_link = True
                        
                    if is_link:
                         # Use JS to open in new tab
                         self.driver.execute_script("window.open(arguments[0], '_blank');", href)
                         time.sleep(2)
                         # Switch to new tab
                         new_window = [w for w in self.driver.window_handles if w != main_window][0]
                         self.driver.switch_to.window(new_window)
                    else:
                         # If it's a dynamic JS app (SPA), we CANNOT easily open in new tab if there's no URL.
                         # Ctrl+Click on element might work if the app listens for it?
                         # Let's try simulating Ctrl+Click.
                         ActionChains(self.driver).key_down(Keys.CONTROL).click(title_el).key_up(Keys.CONTROL).perform()
                         time.sleep(3)
                         
                         # Check if a new window opened
                         handles = self.driver.window_handles
                         if len(handles) > 1:
                              # Success, switch
                              new_window = [w for w in handles if w != main_window][0]
                              self.driver.switch_to.window(new_window)
                         else:
                              # Fallback: We MUST click normally.
                              print("    [Navigation] Opening details (standard click)...")
                              try:
                                  title_el.click()
                              except:
                                  self.driver.execute_script("arguments[0].click();", title_el)
                              
                              time.sleep(4)
                              is_link = False
                              
                    # --- SCRAPE DETAILS (Context Agnostic) ---
                    try:
                         # Save URL
                         item_data['link'] = self.driver.current_url
                         
                         WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                         body_text = self.driver.find_element(By.TAG_NAME, "body").text
                         
                         # Date
                         date_match = re.search(r'Respond By[\s\n]+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}(?:\s+\d{1,2}:\d{2}(?:\s*GMT[+\-]\d{2}:\d{2})?)?)', body_text)
                         if date_match:
                             item_data['published'] = f"Closing: {date_match.group(1)}"
                             item_data['close_date_raw'] = date_match.group(1)
                         
                         # Doc ID
                         doc_match = re.search(r'Sourcing(?: reference)?[\s\-:]*(Doc\d+)', body_text, re.IGNORECASE)
                         if doc_match:
                             item_data['doc_id'] = doc_match.group(1)
                         # RFI / ID
                         # Often appears as "ID - 111..." or "ID: 111...".
                         # Use strict regex with word boundary to avoid matching inside words (e.g. "Orchid" -> id)
                         
                         id_val = None
                         # 1. Try finding ID followed explicitly by digits (user mentioned starting with 111)
                         # e.g. "ID: 111000..."
                         id_match_digits = re.search(r'\b(?:Solicitation\s+)?ID\b\s*[\:\.\-\s]\s*(11\d+)', body_text, re.IGNORECASE)
                         if id_match_digits:
                             id_val = id_match_digits.group(1)
                         else:
                             # 2. Broader match but with word boundary
                             id_match = re.search(r'\b(?:Solicitation\s+)?ID\b\s*[\:\.\-\s]\s*([\w\d\-]+)', body_text, re.IGNORECASE)
                             if id_match:
                                 id_val = id_match.group(1)
                        
                         if id_val:
                              item_data['rfi_id'] = id_val

                         # Buyer
                         company_match = re.search(r'(?:Company|Buyer)\s*[:\.\-]\s*([^\n\r]+)', body_text, re.IGNORECASE)
                         if company_match:
                             item_data['buyer'] = company_match.group(1).strip()

                         # Category (e.g. "Category: Surgical light handle covers")
                         # Only extract if we didn't get it from row
                         if 'category' not in item_data or not item_data['category']:
                             category_match = re.search(r'(?:Product\s+)?Category\s*[:\.\-]\s*([^\n\r]+)', body_text, re.IGNORECASE)
                             if category_match:
                                 item_data['category'] = category_match.group(1).strip()
 
                         item_data['summary'] = body_text[:200].replace('\n', ' ') + "..."

                    except Exception as scrape_e:
                        print(f"    ~ Scrape detail fail: {scrape_e}")
                    
                    # --- RETURN LOGIC ---
                    if len(self.driver.window_handles) > 1:
                        # Close tab
                        self.driver.close()
                        self.driver.switch_to.window(main_window)
                    else:
                        # Go Back (if we didn't open new tab)
                        print("    Going back...")
                        self.driver.back()
                        time.sleep(4)
                        
                except Exception as nav_e:
                    print(f"    [!] Nav error: {nav_e}")
                    items.append(item_data)
                    # If we crashed during nav, ensure we are on main
                    try:
                        if len(self.driver.window_handles) > 1:
                            self.driver.switch_to.window(main_window)
                    except: pass
                    continue

                if item_data['title'] != 'N/A':
                    items.append(item_data)
                
            return items

        except Exception as e:
            print(f"  [!] Extraction error: {e}")
            return []

    def extract_data(self, max_pages=10):
        all_items = []
        seen_identifiers = set() 
        
        expected_total = 9999
        try:
             headers = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'results for')]")
             for h in headers:
                 txt = h.text
                 match = re.search(r'(\d+)\s+results\s+for', txt, re.IGNORECASE)
                 if match:
                     expected_total = int(match.group(1))
                     print(f"[Pagination] Identified Total Results: {expected_total}")
                     break
        except:
             pass

        previous_first_item_text = None

        for page in range(max_pages):
            print(f"[Pagination] Page {page+1}/{max_pages} (Collected: {len(all_items)}/{expected_total})")
            
            # Scrape current page
            page_items = self._scrape_current_page()
            
            # Deduplicate & Add
            new_items_count = 0
            current_first_item_text = ""
            
            if page_items:
                 current_first_item_text = page_items[0].get('title', '') + page_items[0].get('rfi_id', '')

                 for item in page_items:
                     uid = item.get('rfi_id')
                     if not uid:
                         uid = item.get('title', '') + "_" + item.get('published', '')
                     
                     if uid not in seen_identifiers:
                         seen_identifiers.add(uid)
                         all_items.append(item)
                         new_items_count += 1
            
            print(f"  + Added {new_items_count} new items (Total Unique: {len(all_items)})")
            
            if len(all_items) >= expected_total:
                print("  [Pagination] Reached expected total. Stopping.")
                break
            
            if not page_items or new_items_count == 0:
                 if len(page_items) > 0 and new_items_count == 0:
                      print("  [Pagination] All items on this page are duplicates. Stopping.")
                      break
                 if not page_items:
                      print("  [Pagination] No items found on this page. Stopping.")
                      break

            # Check for Next / Go to specific page
            if page < max_pages - 1: # Don't click next on last page
                
                # ENFORCE SEARCH CONTEXT before moving
                # User report: Search resets on paging. Re-apply to ensure we get filtered results.
                print("  [Pagination] Verifying search context...")
                self.ensure_search_context("Singapore")
                
                next_page_num = page + 2 # page is 0-indexed (0=Page 1), so next is Page 2.
                print(f"  [Pagination] Attempting to go to Page {next_page_num}...")
                
                if not self._go_to_page(next_page_num):
                    print(f"  [Pagination] Could not click Page {next_page_num} button. Trying generic 'Next'...")
                    if not self._go_next_page():
                         print("  [Pagination] No next page or limit reached.")
                         break
                
                # Wait for content change
                print("  [Pagination] Waiting for next page content...")
                
                # Robust Wait: Wait until first item changes
                start_wait = time.time()
                page_changed = False
                while time.time() - start_wait < 10: 
                    try:
                            # Use STRICT selector
                            try:
                                first_title_el = self.driver.find_element(By.CSS_SELECTOR, ".sapMObjectIdentifierTitle .sapMLnk")
                            except:
                                first_title_el = self.driver.find_element(By.CSS_SELECTOR, "a[id*='title']")
                                
                            new_text = first_title_el.text.strip()
                            
                            # Only confirm change if new_text is valid and different
                            if new_text and new_text != page_items[0].get('title', '').strip():
                                page_changed = True
                                break
                    except:
                            pass
                    time.sleep(0.5)
                
                if page_changed:
                        print("  [Pagination] Content change detected.")
                        time.sleep(2)
                else:
                        print("  [Pagination] Warning: Content did not appear to change (or identical top item). Continuing anyway...")
        
        return all_items

    def ensure_search_context(self, keyword):
        """
        Checks if the search box contains the keyword. If not, re-enters it.
        This prevents 'ghost' entries appearing if the context was lost.
        """
        try:
            inp = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='Search']")))
            val = inp.get_attribute("value")
            
            # Case insensitive check
            if keyword.lower() not in val.lower():
                print(f"  [Search] Context lost (Value: '{val}'). Re-applying '{keyword}'...")
                inp.clear()
                inp.send_keys(keyword)
                inp.send_keys(Keys.ENTER)
                time.sleep(5) # Wait for reload
                
                # Re-sort might be needed too?
                # User says: "reapply search filter ... then click to page 2"
                # If we re-search, it usually resets to Page 1.
                # So if we are about to go to Page 2, and we re-search, we become at Page 1.
                # Then `_go_to_page(2)` should work fine from Page 1.
            else:
                # print("  [Search] Context valid.")
                pass

        except Exception as e:
            print(f"  [Search] Error ensuring context: {e}")

    def _go_to_page(self, page_num):
        """
        Clicks the specific page number button (e.g. '2', '3').
        """
        try:
            target_btn = None
            
            # Search for element with exact text
            candidates = self.driver.find_elements(By.XPATH, f"//*[text()='{page_num}']")
            
            for c in candidates:
                if not c.is_displayed(): continue
                parent = c
                found_btn = False
                for _ in range(4): # Check 4 levels up
                    try:
                        parent = parent.find_element(By.XPATH, "./..")
                        tag = parent.tag_name
                        cls = parent.get_attribute("class")
                        
                        if tag == "button" or "btn" in cls.lower() or "pagin" in cls.lower():
                             if "sapMBtnDisabled" in cls:
                                  print(f"  [Pagination] Page {page_num} button found but disabled.")
                                  return False
                             
                             target_btn = parent
                             found_btn = True
                             break
                    except:
                        break
                
                if found_btn:
                    break
            
            if not target_btn:
                 btns = self.driver.find_elements(By.XPATH, f"//button[contains(., '{page_num}')]")
                 for b in btns:
                     if b.text.strip() == str(page_num) and b.is_displayed():
                         target_btn = b
                         break

            if target_btn:
                print(f"  [Pagination] Clicking Page {page_num} button...")
                try:
                    target_btn.click()
                except:
                    self.driver.execute_script("arguments[0].click();", target_btn)
                
                # Wait for button to become selected/active/emphasized?
                # Ariba usually adds 'sapMBtnTransparent' vs 'sapMBtnEmphasized'
                # But sometimes it's `sapMBtnDisabled` if it's the current page?
                # Or the number becomes bold.
                return True
            else:
                print(f"  [Pagination] Page {page_num} button NOT found.")
                return False

        except Exception as e:
            print(f"  [Pagination] Error navigating to page {page_num}: {e}")
            return False

    def _go_next_page(self):
         # Logic to find and click next
         try:
             # Strategy: Look for button with title 'slim-arrow-right' (standard Ariba icon name)
             # Also check for 'Next' just in case.
             
             next_btn = None
             
             # 1. Try Title 'slim-arrow-right' or 'Next'
             candidates = self.driver.find_elements(By.XPATH, "//button[contains(@title, 'arrow-right')] | //button[@title='Next']")
             
             for btn in candidates:
                 if not btn.is_displayed(): continue
                 
                 # Check disabled state
                 classes = btn.get_attribute("class")
                 if "sapMBtnDisabled" in classes or "disabled" in classes:
                     continue
                     
                 next_btn = btn
                 break
            
             if not next_btn:
                  # 2. Fallback: Last button in a paginator container if explicit title fails
                  # But looking at debug, title seems reliable.
                  pass

             if next_btn:
                 print("  [Pagination] Clicking Next (slim-arrow-right)...")
                 try:
                     next_btn.click()
                 except:
                     self.driver.execute_script("arguments[0].click();", next_btn)
                 return True
             
         except Exception as e:
             print(f"  [Pagination] Next error: {e}")
         
         return False

    def check_for_login(self):
        try:
            # Check for "Explore Leads" button on login page
            explore_btns = self.driver.find_elements(By.XPATH, "//button[contains(., 'Explore Leads')] | //a[contains(., 'Explore Leads')]")
            for btn in explore_btns:
                if btn.is_displayed():
                    print("  [Login Wall] Found 'Explore Leads' button. Clicking...")
                    btn.click()
                    time.sleep(5)
                    return True
        except Exception as e:
            print(f"  [Login Check] Info: {e}")
        return False

# Wrapper for app.py
def fetch_ariba_opportunities(headless=True, date_mode='today', date_start=None, date_end=None, max_pages=10):
    scraper = AribaScraper(headless=headless)
    try:
        scraper.nav_to_search()
        scraper.search_keyword("Singapore")
        scraper.sort_results("Newest Leads")
        
        # Calculate optimal preset for custom range
        preset_mode = date_mode
        days_diff = None
        
        if (date_mode == 'custom' or date_mode == 'specific_date') and date_start:
            try:
                # If we have start date, calculate days from now
                start_dt = datetime.strptime(date_start, '%Y-%m-%d')
                diff = datetime.now() - start_dt
                days_diff = diff.days + 1 # Include start day (Age of the start date)
                
                # Check for negative (future dates?) or zero
                if days_diff < 1: days_diff = 1
                
                print(f"[Wrapper] Custom Range (Start Date Age: {days_diff} days) -> Auto-mapping")
            except Exception as e:
                print(f"[Wrapper] Date calc error: {e}")
                pass

                
        # Use calculated preset
        # We pass 'custom' or original mode, but with 'days' populated so apply_date_filter logic kicks in
        scraper.apply_date_filter(mode=date_mode, days=days_diff)

        
        items = scraper.extract_data(max_pages=max_pages)
        return items
    except Exception as e:
        print(f"[Wrapper Error] {e}")
        return []
    finally:
        scraper.close()

if __name__ == "__main__":
    print("Running Ariba V2 Test...")
    # Test wrapper
    # items = fetch_ariba_opportunities(headless=False)
    # print(f"Captured {len(items)} items")

    scraper = AribaScraper(headless=False)
    try:
        scraper.nav_to_search()
        scraper.search_keyword("Singapore")
        scraper.sort_results("Newest Leads")
        scraper.apply_date_filter(mode="custom", days=20) # Test custom mapping (should be 31 days)

        # scraper.apply_date_filter(days=7) # Optional
        results = scraper.extract_data()
        
        print(f"\nCaptured {len(results)} results:")
        for r in results:
            print(f" - {r['title']} ({r['published']})")
            
    except Exception as e:
        print(f"CRASH: {e}")
    finally:
        # scraper.close()
        print("Done. Browser left open for inspection.")
