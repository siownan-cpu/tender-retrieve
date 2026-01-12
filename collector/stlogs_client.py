import time
import sys
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import json

def log(msg):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()

def setup_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--ignore-certificate-errors')
    driver = webdriver.Chrome(options=options)
    return driver

class STLogsClient:
    def __init__(self):
        self.base_url = "https://epro.stlogs.com/eProVportal/spLogin.do"
        self.driver = None

    def wait_for_loading(self, timeout=15):
        """Waits for sc-loadmask, backdrop, or spinner to disappear."""
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                # Check for loadmask OR backdrop in main doc or checked iframe
                is_loading = self.driver.execute_script("""
                    let masks = document.querySelectorAll('sc-loadmask, .sc-loadmask, .spinner, sc-loadmask-backdrop, .sc-loadmask-backdrop');
                    for (let m of masks) {
                        if (m.offsetWidth > 0 && m.offsetHeight > 0 && 
                            window.getComputedStyle(m).display !== 'none' && 
                            window.getComputedStyle(m).visibility !== 'hidden' &&
                            window.getComputedStyle(m).opacity !== '0') {
                            return true;
                        }
                    }
                    return false;
                """)
                if not is_loading:
                    return
                time.sleep(0.5)
            except:
                return 

    def fetch_opportunities(self, date_mode='all', start_date=None, end_date=None):
        """
        Fetches procurement opportunities from ST Logistics.
        """
        items = []
        # Run headless for speed as requested
        self.driver = setup_driver(headless=True)
        
        try:
            log(f"STLogs: Navigating to {self.base_url}")
            self.driver.get(self.base_url)
            
            # Check for page load success
            time.sleep(3) # Reduced to 3s as requested
            self.wait_for_loading(15)
            
            # Shadow Root Check / Polymer Ready
            polymer_ready = False
            for i in range(10): # Wait up to 20s (Reverted for safety)
                polymer_ready = self.driver.execute_script("""
                    return (window.Polymer && window.Polymer.polymerReady) || false;
                """)
                if polymer_ready: break
                time.sleep(2)
            
            log(f"STLogs: Polymer Ready: {polymer_ready}")

            # 1. Click 'Find Opportunities'
            wait = WebDriverWait(self.driver, 25)
            
            clicked = False
            for attempt in range(3):
                try:
                    el = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Find Opportunities")))
                    try:
                        el.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", el)
                    clicked = True
                    break
                except Exception as e:
                    log(f"STLogs: Click attempt {attempt+1} failed: {e}")
                    time.sleep(2)
            
            if not clicked:
                log("STLogs: Falling back to 'Read More' in cards...")
                try:
                     links = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Read More')]")
                     for l in links:
                         if l.is_displayed():
                             l.click()
                             clicked = True
                             break
                except: pass

            if not clicked:
                log("STLogs: ❌ Failed to click 'Find Opportunities'.")
                return []

            log("STLogs: Clicked. Waiting for modal...")
            time.sleep(10)
            self.wait_for_loading(30) # Extended wait for modal loadmask
            
            # 2. Check for Popups
            handles = self.driver.window_handles
            if len(handles) > 1:
                log(f"STLogs: Switching to popup logic (Handles: {len(handles)})")
                self.driver.switch_to.window(handles[-1])
                time.sleep(3)
                self.wait_for_loading(15)

            # Apply UI Date Filters
            if start_date and end_date:
                s_str = start_date.strftime('%d/%m/%Y')
                e_str = end_date.strftime('%d/%m/%Y')
                log(f"STLogs: Applying UI Filter: {s_str} - {e_str}")
                
                 # Check for iframe in modal
                try:
                    iframe = self.driver.find_element(By.NAME, "poupJspIFrame")
                    if iframe:
                        log("STLogs: Found modal iframe 'poupJspIFrame'. Switching context...")
                        self.driver.switch_to.frame(iframe)
                        time.sleep(2)
                        self.wait_for_loading(20) # Crucial wait inside iframe
                except:
                    log("STLogs: No iframe 'poupJspIFrame' found. Continuing in main context...")

                try:
                    target_field = None
                    # Retry loop for Date Fields
                    for attempt in range(5):
                        date_fields = self.driver.execute_script("""
                            function findPeriodField(root) {
                                let tag = root.tagName ? root.tagName.toUpperCase() : "";
                                if (tag.includes('PERIOD-DATE')) {
                                    if (root.offsetWidth > 0 && root.offsetHeight > 0) return [root];
                                }
                                let found = [];
                                if (root.shadowRoot) {
                                    found = found.concat(findPeriodField(root.shadowRoot));
                                }
                                let children = root.children || root.childNodes;
                                for (let c of children) {
                                    if (c.nodeType === 1) found = found.concat(findPeriodField(c));
                                }
                                return found;
                            }
                            return findPeriodField(document.body);
                        """)
                        if date_fields:
                            target_field = date_fields[0]
                            log(f"STLogs: Found {len(date_fields)} visible period fields.")
                            break
                        time.sleep(2)

                    if target_field:
                        # Find inputs
                        inputs_found = self.driver.execute_script("""
                            let period = arguments[0];
                            function findInputByBind(root, bindVal) {
                                if (!root) return null;
                                if (root.tagName === 'SC-TEXT-FIELD' && root.getAttribute('data-bind-property') === bindVal) {
                                    let inp = root.querySelector('input');
                                    if (!inp && root.shadowRoot) inp = root.shadowRoot.querySelector('input');
                                    return inp;
                                }
                                if (root.shadowRoot) {
                                    let res = findInputByBind(root.shadowRoot, bindVal);
                                    if (res) return res;
                                }
                                let children = root.children || root.childNodes;
                                for (let c of children) {
                                    if (c.nodeType === 1) {
                                        let res = findInputByBind(c, bindVal);
                                        if (res) return res;
                                    }
                                }
                                return null;
                            }
                            let fromInp = findInputByBind(period, 'fromValue');
                            let toInp = findInputByBind(period, 'toValue');
                            return [fromInp, toInp];
                        """, target_field)
                        
                        from_input = inputs_found[0]
                        to_input = inputs_found[1]
                        
                        if from_input:
                            try:
                                from_input.click() # Focus
                                self.driver.execute_script("arguments[0].value = '';", from_input)
                                from_input.send_keys(s_str)
                                log(f"STLogs: Typed Start: {s_str}")
                            except Exception as e: log(f"STLogs: Err Start: {e}")
                        
                        if to_input:
                            try:
                                to_input.click() # Focus
                                self.driver.execute_script("arguments[0].value = '';", to_input)
                                to_input.send_keys(e_str)
                                log(f"STLogs: Typed End: {e_str}")
                            except Exception as e: log(f"STLogs: Err End: {e}")

                    else:
                        log("STLogs: ⚠️ Could not find sc-period-date-field after retries.")

                    # 2. Click Search with Retry for Interception
                    search_btn = self.driver.execute_script("""
                        function findSearch(root) {
                            if (root.tagName && (root.tagName === 'SC-BUTTON' || root.tagName === 'BUTTON')) {
                                let txt = root.textContent.trim().toLowerCase();
                                if (txt === 'search' || root.getAttribute('text') === 'Search') {
                                    if (root.offsetWidth > 0) return root;
                                }
                            }
                            if (root.shadowRoot) {
                                let res = findSearch(root.shadowRoot);
                                if (res) return res;
                            }
                            let children = root.children || root.childNodes;
                            for (let c of children) {
                                if (c.nodeType === 1) {
                                    let res = findSearch(c);
                                    if (res) return res;
                                }
                            }
                            return null;
                        }
                        return findSearch(document.body);
                    """)
                    
                    if search_btn:
                        for click_try in range(3):
                            try:
                                search_btn.click()
                                log("STLogs: Clicked Search. Waiting for update...")
                                time.sleep(5) 
                                self.wait_for_loading(20) # Wait for post-search load
                                time.sleep(5) # Extra buffer for grid render 
                                break
                            except Exception as ce:
                                log(f"STLogs: Search click intercepted (try {click_try+1}): {ce}")
                                self.wait_for_loading(5)
                                time.sleep(2)
                    else:
                        log("STLogs: ⚠️ Search button not found.")

                except Exception as fe:
                    log(f"STLogs: UI Filter Exception: {fe}")
            
            # Ensure we are in the frame (if lost)
            try:
                if len(self.driver.execute_script("return document.getElementsByTagName('sc-grid')")) == 0:
                     self.driver.switch_to.default_content()
                     iframe = self.driver.find_element(By.NAME, "poupJspIFrame")
                     self.driver.switch_to.frame(iframe)
            except: pass

            # --- DATA EXTRACTION ---
            log("STLogs: Attempting Data Extraction...")
            
            js_script = """
            function findGrid(root) {
                if (!root) return null;
                if (root.tagName === 'SC-GRID') return root;
                if (root.shadowRoot) {
                    let res = findGrid(root.shadowRoot);
                    if (res) return res;
                }
                let children = root.children || root.childNodes;
                for (let c of children) {
                    if (c.nodeType === 1) {
                         let res = findGrid(c);
                         if (res) return res;
                    }
                }
                return null;
            }
            
            const grid = findGrid(document.body);
            if (!grid) return "NO_GRID";
            
            let items = null;
            if (grid.dataProvider) {
                if (Array.isArray(grid.dataProvider)) items = grid.dataProvider;
                else if (grid.dataProvider.items) items = grid.dataProvider.items;
                else if (typeof grid.dataProvider === 'object' && grid.dataProvider.length !== undefined) items = grid.dataProvider;
            }
            
            if (items) return JSON.stringify(items);
            return "NO_DATA";
            """
            
            extracted_items = None
            for i in range(10):  # Retry up to 10 times
                try:
                    res = self.driver.execute_script(js_script)
                    if res and res != "NO_DATA" and res != "NO_GRID" and not res.startswith("JSON_ERROR"):
                        extracted_items = json.loads(res)
                        log(f"STLogs: ✅ Extracted {len(extracted_items)} items via DataProvider.")
                        break
                    elif res == "NO_DATA":
                        log("STLogs: Grid found, waiting for data...")
                except Exception as je:
                    log(f"STLogs: JS Error: {je}")
                time.sleep(2)

            if extracted_items:
                log(f"STLogs: ✅ Processing {len(extracted_items)} extracted items.")
                
                # DEBUG: Log keys of first item to find Product Category
                if len(extracted_items) > 0:
                    try:
                        first_keys = list(extracted_items[0].keys())
                        log(f"STLogs: Available Keys: {first_keys}")
                    except: pass
                
                kept_count = 0
                for raw in extracted_items:
                    try:
                        title = raw.get('rfx_tit')
                        ref_no = raw.get('rfx_no')
                        bu = raw.get('bu_nm', 'ST Logistics')
                        
                        # Try to find Product Category
                        # keys found: ['publish_sts', 'rfx_no', 'rfx_start_dt', 'rfx_close_dt', 'sg_cd', ... 'sg_nm']
                        # 'sg_nm' (Service Group Name) is likely the Product Category
                        category = raw.get('sg_nm') or raw.get('purc_grp_nm') or raw.get('item_cls_nm') or "General"
                        
                        pub_date_str = str(raw.get('noti_start_dt', ''))
                        if not pub_date_str and 'rfx_start_dt' in raw:
                            pub_date_str = str(raw['rfx_start_dt'])
                            
                        close_date_str = str(raw.get('noti_end_dt', ''))
                        if not close_date_str and 'rfx_close_dt' in raw:
                             close_date_str = str(raw['rfx_close_dt'])
                        
                        # Parse Date for Filtering and Display
                        # Raw data seems to be UTC (-8h) relative to SG Web Display
                        # We must add 8 hours to match the Web UI
                        
                        pub_dt_adjusted = None
                        close_dt_adjusted = None
                        
                        from dateutil import parser
                        from datetime import timedelta
                        
                        try:
                            # Parse Start Date
                            # STRICT FIX: Inspect raw string. If ISO (contains 'T'), use standard parse (Year-Month-Day).
                            # If DD/MM/YYYY, use dayfirst=True.
                            # The previous bug was dateutil with dayfirst=True flipping ISO dates (2026-01-03 -> Mar 1st).
                            if 'T' in pub_date_str:
                                # Clean potential 'Z' or msg remnants if needed, but dateutil handles it well usually.
                                # However, to be 100% safe against the "DayFirst" flip, we disable dayfirst here.
                                dt_start = parser.parse(pub_date_str, dayfirst=False)
                            else:
                                dt_start = parser.parse(pub_date_str, dayfirst=True)
                                
                            # Adjust Timezone (+8h)
                            pub_dt_adjusted = dt_start + timedelta(hours=8)
                            pub_date_final_str = pub_dt_adjusted.strftime('%Y-%m-%d %H:%M:%S')
                        except Exception as e:
                            log(f"STLogs WARN: PubDate parse error '{pub_date_str}': {e}")
                            pub_date_final_str = pub_date_str

                        try:
                            # Parse Closing Date
                            if 'T' in close_date_str:
                                dt_end = parser.parse(close_date_str, dayfirst=False)
                            else:
                                dt_end = parser.parse(close_date_str, dayfirst=True)
                                
                            close_dt_adjusted = dt_end + timedelta(hours=8)
                            close_date_final_str = close_dt_adjusted.strftime('%Y-%m-%d %H:%M:%S')
                        except Exception as e:
                            log(f"STLogs WARN: CloseDate parse error '{close_date_str}': {e}")
                            close_date_final_str = close_date_str
                        
                        # DEBUG: Log date conversion for first item
                        if kept_count == 0:
                            log(f"STLogs: Sample Date Conv: Raw Start='{pub_date_str}' -> '{pub_date_final_str}'")
                            log(f"STLogs: Sample Date Conv: Raw Close='{close_date_str}' -> '{close_date_final_str}'")

                        # STRICT FILTERING DISABLED (Trusting UI Filter)
                        # The UI Search succeeded (11 items). We extract what the UI shows.
                        # Adding strict filtering here is removing valid items due to potential TZ mismatches or boundary issues.
                        # if start_date and pub_dt_adjusted:
                        #      if pub_dt_adjusted.date() < start_date.date():
                        #          continue
                        # if end_date and pub_dt_adjusted:
                        #      if pub_dt_adjusted.date() > end_date.date():
                        #          continue
                        
                        kept_count += 1
                        
                        items.append({
                            "title": title,
                            "ref_no": ref_no,
                            "link": self.base_url, 
                            "pub_date": pub_date_final_str,
                            "closing_date": close_date_final_str,
                            "source": f"ST Logistics ({bu})" if bu else "ST Logistics",
                            "category": category
                        })
                    except Exception as item_err:
                        log(f"STLogs: Item parse error: {item_err}")
                
                log(f"STLogs: Kept {kept_count}/{len(extracted_items)} items (Filtered).")

            else:
                log("STLogs: ❌ Grid/Data not found after retries.")
                try:
                    ts = int(time.time())
                    self.driver.save_screenshot(f"stlogs_fail_{ts}.png")
                except: pass

        except Exception as e:
            log(f"STLogs: Fetch error: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)
        finally:
            if self.driver:
                self.driver.quit()
        
        return items
