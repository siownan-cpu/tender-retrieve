
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

class AribaScraper:
    def __init__(self, headless=True):
        self.driver = self._setup_driver(headless)
        self.wait = WebDriverWait(self.driver, 15)
        self.base_url = 'https://portal.us.bn.cloud.ariba.com/dashboard/public/appext/comsapsbncdiscoveryui#/leads/search?anId=ANONYMOUS'

    def _setup_driver(self, headless):
        options = Options()
        if headless:
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        return webdriver.Chrome(options=options)

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
        elif mode == 'custom' or mode == 'specific_date':
            # Map Custom/Specific -> Last 365 Days (as requested)
            target = "Last 365 days"
        elif mode == 'last_7_days' or days == 7: 
            target = "Last 7 days"
        elif mode == 'last_14_days' or days == 14: 
            target = "Last 14 days"
        elif mode == 'last_31_days' or days == 31: 
            target = "Last 31 days"
        elif mode == 'last_90_days' or days == 90:
            target = "Last 90 days"
        elif mode == 'last_365_days' or days == 365:
            target = "Last 365 days"
            
        print(f"[Filter] Mapped mode '{mode}' to Ariba option '{target}'")

        try:
             # Find "Date Posted" dropdown
            dd = None
            # Locate by label near it
            try:
                # Use strict XPath based on prev debug
                dd = self.driver.find_element(By.XPATH, "//label[contains(., 'Date Posted')]/following::div[contains(@class, 'sapMSlt')][1]")
            except:
                pass
            
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

    def extract_data(self):
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

                # 1. Get List View Info
                try:
                    # Scroll into view
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
                    time.sleep(0.2)

                    title_el = row.find_element(By.CSS_SELECTOR, ".sapMObjectIdentifierTitle .sapMLnk, a.sapMLnk, a[id*='title']")
                    item_data['title'] = title_el.text.strip()
                    
                    if not item_data['title']:
                         # Try getting inner text or title attribute
                         item_data['title'] = title_el.get_attribute("textContent").strip()
                except Exception as e:
                    # print(f"    ~ Title extract fail: {e}")
                    continue # Skip if no title
                
                if "Mock" in item_data['title']: continue

                print(f"  Processing [{i+1}]: {item_data['title'][:40]}...")

                # 2. Get Details via Click -> Back
                try:
                    # Click title
                    try:
                        title_el.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", title_el)
                    
                    time.sleep(5) # Wait for page load
                    
                    # Scrape Details
                    try:
                         # Verify we are on details
                        if "leads/search" in self.driver.current_url:
                            print("    [!] Failed to navigate to details (still on search)")
                            items.append(item_data)
                            continue

                        item_data['link'] = self.driver.current_url
                        
                        # Body
                        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                        body_text = self.driver.find_element(By.TAG_NAME, "body").text
                        
                        # Date
                        date_match = re.search(r'Respond By[\s\n]+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}(?:\s+\d{1,2}:\d{2})?)', body_text)
                        if date_match:
                            item_data['published'] = f"Closing: {date_match.group(1)}"
                        
                        item_data['summary'] = body_text[:200].replace('\n', ' ') + "..."
                        
                    except Exception as scrape_e:
                        print(f"    ~ Scrape detail fail: {scrape_e}")

                    # Go Back
                    self.driver.back()
                    print("    Going back...")
                    time.sleep(5) # Valid wait for SAP reload

                    # Verify State (Search & Sort)
                    # 1. Search
                    try:
                        # Wait for search box
                        inp = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='Search']")))
                        val = inp.get_attribute("value")
                        if "Singapore" not in val:
                            print("    [!] Search lost. Re-applying...")
                            inp.clear()
                            inp.send_keys("Singapore")
                            inp.send_keys(Keys.ENTER)
                            time.sleep(5)
                            # If we re-search, we must re-sort
                            self.sort_results("Newest Leads")
                    except:
                        pass
                    
                    # 2. Sort (Optional check, but good if we want strictness)
                    # We assume if we didn't lose search, we might not have lost sort.
                    # But often it resets to Relevance.
                    # Let's check text of the active sort dropdown if possible? 
                    # For now, let's just proceed. The "Re-sort if lost search" covers the big reset case.

                except Exception as nav_e:
                    print(f"    [!] Nav error: {nav_e}")
                    items.append(item_data)
                    continue

                if item_data['title'] != 'N/A':
                    items.append(item_data)
                
            return items

        except Exception as e:
            print(f"  [!] Extraction error: {e}")
            return []

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

if __name__ == "__main__":
    print("Running Ariba V2 Test...")
    scraper = AribaScraper(headless=False)
    try:
        scraper.nav_to_search()
        scraper.search_keyword("Singapore")
        scraper.sort_results("Newest Leads")
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
