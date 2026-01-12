
import time
import re
from datetime import datetime
from dateutil import parser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

from util.driver_setup import get_chrome_driver
class GeBizClient:
    def setup_driver(self, headless=True):
        """Setup Chrome WebDriver with options"""
        return get_chrome_driver(headless)

    def get_text_safe(self, element):
        try:
            return element.text.strip()
        except:
            return ""

    def _extract_page_items(self, driver, start_date=None, end_date=None, search_type='BO'):
        """
        Extracts items from the current results page.
        Returns: (items, stop_signal)
        stop_signal is True if we encountered an item older than start_date (strictly).
        """
        items = []
        stop_signal = False
        
        # Find item containers (div.formColumns_MAIN)
        potential_containers = driver.find_elements(By.CSS_SELECTOR, "div.formColumns_MAIN")
        
        valid_count = 0
        
        for container in potential_containers:
            try:
                # Check if this container has a title link
                try:
                    title_el = container.find_element(By.CSS_SELECTOR, "a.commandLink_TITLE-BLUE")
                except NoSuchElementException:
                    continue # Not an item container
                
                title = title_el.text.strip()
                link = title_el.get_attribute("href")
                
                # Extract using robust regex
                full_text = container.text
                
                # Document No / Reference No
                # Format: "1   Tender - NST000ETT26000001 / T/ISCE2/13/FY25"
                document_no = ""
                
                # Strategy 1: Extract from Link (Most reliable for Doc Code)
                # Link: .../directlink.xhtml?docCode=DEF005ETQ26000001
                if link:
                    m_link = re.search(r'docCode=([A-Za-z0-9]+)', link)
                    if m_link:
                        document_no = m_link.group(1).strip()
                        
                # Strategy 2: Regex from Header Text (if link failed)
                if not document_no:
                    m_doc_header = re.search(r'(?:-|–)\s*([A-Za-z0-9]+)', full_text)
                    if m_doc_header:
                         document_no = m_doc_header.group(1).strip()
                
                # Strategy 3: Specific keywords
                if not document_no:
                     m_doc = re.search(r'(?:Document|Quotation|Tender|ITT|ITQ)\s*(?:No\.?)?[\s:\-]+([A-Za-z0-9\-/]+)', full_text, re.IGNORECASE)
                     if m_doc: document_no = m_doc.group(1).strip()

                # Secondary Reference (e.g. "/ ITQ ref no. 2025501411")
                # Append if found
                m_sec = re.search(r'/\s*(?:ITQ|ITT|Ref|PR|No\.)\s*(?:ref|no\.?)?\s*([A-Za-z0-9\-/]+)', full_text, re.IGNORECASE)
                if m_sec:
                    sec_ref = m_sec.group(1).strip()
                    if sec_ref and sec_ref not in document_no:
                        document_no = f"{document_no} / {sec_ref}" if document_no else sec_ref
                    
                # Category
                category = "Business Opportunities"
                m_cat = re.search(r'(?:Category|Procurement Type|Procurement Category)[\s:]+(.*?)(?:\n|$)', full_text, re.IGNORECASE)
                if m_cat: category = m_cat.group(1).strip()
                    
                # Closing Date
                # Format: "Closing on 29 Jan 2026 04:00PM" (Right side)
                # Regex handles newlines and spaces greedy
                close_date_str = ""
                # Pattern: Closing on/Date ... dd MMM yyyy ... HH:MMPM
                m_close = re.search(r'(?:Closing on|Closing Date|Closed)[\s\S]*?(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})[\s]*(\d{1,2}:\d{2}\s?[AP]M)', full_text, re.IGNORECASE)
                if m_close:
                     close_date_str = f"{m_close.group(1).strip()} {m_close.group(2).strip()}"
                
                # Published Date
                pub_date_str = ""
                pub_date = None
                
                m_pub = re.search(r'(?:Published|Posted)[\s\S]*?(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})[\s]*(\d{1,2}:\d{2}\s?[AP]M)', full_text, re.IGNORECASE)
                if m_pub:
                     pub_date_str = f"{m_pub.group(1).strip()} {m_pub.group(2).strip()}"
                else:
                    # Fallback simplier
                    m_pub_simple = re.search(r'(?:Published|Posted)[\s:]+(.*?)(?:\n|$)', full_text, re.IGNORECASE)
                    if m_pub_simple: pub_date_str = m_pub_simple.group(1).strip()
                
                if pub_date_str:
                        try:
                            from dateutil import parser as dparser
                            pub_date = dparser.parse(pub_date_str, fuzzy=True)
                        except: pass
                
                # Agency
                agency = "Unknown"
                m_agency = re.search(r'Agency[\s:]+(.*?)(?:\n|$)', full_text)
                if m_agency: agency = m_agency.group(1).strip()
                
                # --- Award Fields ---
                awarded_to = ""
                award_value = ""
                awarded_date_str = ""
                
                # Awarded To
                # Look for "Awarded to" followed by content
                m_awd_to = re.search(r'Awarded to[\s\r\n]+(.*?)(?:\r?\n|$)', full_text, re.IGNORECASE)
                if m_awd_to: 
                    # Clean up if it grabbed too much (e.g. stopped at newline)
                    # If the next line is "Award Value", we are good.
                    awarded_to = m_awd_to.group(1).strip()

                # Award Value
                m_awd_val = re.search(r'Award Value[\s\r\n]+(.*?)(?:\r?\n|$)', full_text, re.IGNORECASE)
                if m_awd_val:
                    award_value = m_awd_val.group(1).strip()
                
                # Awarded Date
                # Explicitly look for "Awarded" followed by Date (not in a status badge)
                # Regex: Awarded\n05 Jan 2026
                # Or "Awarded Date: ..."
                m_awd_dt = re.search(r'Awarded[\s\r\n]+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', full_text)
                if m_awd_dt:
                    awarded_date_str = m_awd_dt.group(1).strip()
                
                # --- Date Filtering Logic ---
                # DISABLE internal stop signal. Trust GeBIZ Search + Post-Filter.
                # Premature stopping here causes issues if sort order is mixed or parsing is flaky.
                # if start_date and pub_date:
                #     if pub_date < start_date:
                #         print(f"  [Date Check] Item date {pub_date} < Start {start_date}. Stop signal IGNORED to ensure full fetch.")
                #         pass 
                        # stop_signal = True
                
                # Upper bound check (End Date)
                if end_date and pub_date and pub_date > end_date:
                    continue # Skip this item, but don't stop (could be newer items mixed in?)
                    
                items.append({
                    "title": title,
                    "link": link,
                    "agency": agency,
                    "publish_date_str": pub_date_str,
                    "closing_date_str": close_date_str,
                    "source": "gebiz_selenium",
                    "pub_dt": pub_date,
                    "document_no": document_no,
                    "category": category,
                    "awarded_to": awarded_to,
                    "award_value": award_value,
                    "awarded_date_str": awarded_date_str,
                    "search_type": search_type
                })
                valid_count += 1
                
                if stop_signal:
                    break

            except Exception as e:
                # print(f"GeBizClient: Error parsing item: {e}")
                continue

        return items, stop_signal

    def fetch_advanced(self, start_date=None, end_date=None, categories=None, search_type='BO', headless=True):
        """
        Perform Advanced Search.
        search_type: 'BO' (Business Opportunities) or 'AWD' (Awards)
        categories: List of category names (e.g. ['Construction', 'IT Services'])
        """
        driver = self.setup_driver(headless=headless)
        items = []
        
        url = "https://www.gebiz.gov.sg/ptn/opportunity/BOAdvancedSearch.xhtml?origin=opportunities"
        print(f"GeBizClient: Advanced Search ({search_type}) for {len(categories) if categories else 0} categories...")
        print(f"  Range: {start_date} to {end_date}")
        
        try:
            driver.get(url)
            wait = WebDriverWait(driver, 20)
            
            # 1. Select Procurement Category (Multi-select)
            if categories:
                print(f"  Selecting categories: {categories}")
                try:
                    time.sleep(3)
                    
                    dropdown_xpath = "//label[contains(.,'Procurement Category')]/following::input[contains(@class, 'selectManyMenu_BUTTON')][1]"
                    trigger = wait.until(EC.element_to_be_clickable((By.XPATH, dropdown_xpath)))
                    
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", trigger)
                    trigger.click()
                    
                    time.sleep(2) 
                    
                    panels = driver.find_elements(By.CSS_SELECTOR, "div.selectManyMenu_MENULIST_DIV")
                    panel = None
                    for p in panels:
                        if p.is_displayed():
                            panel = p
                            break
                    
                    if not panel:
                        panel = driver.find_element(By.CSS_SELECTOR, "div.ui-selectcheckboxmenu-panel[style*='display: block']")
                    
                    options = panel.find_elements(By.TAG_NAME, "label")
                    
                    for opt in options:
                        txt = opt.text.strip()
                        should_click = False
                        
                        for cat_str in categories:
                            target_main = None
                            target_sub = cat_str
                            
                            if ' > ' in cat_str:
                                parts = cat_str.split(' > ', 1)
                                target_main = parts[0].strip()
                                target_sub = parts[1].strip()
                            
                            if target_sub.lower() == txt.lower():
                                if target_main:
                                    checkbox_id = opt.get_attribute("for") or ""
                                    words = [w for w in re.split(r'[\s,&]+', target_main) if len(w) > 3]
                                    if not words: words = [target_main] 
                                    
                                    if any(w.lower() in checkbox_id.lower() for w in words):
                                        should_click = True
                                        break
                                else:
                                    should_click = True
                                    break
                        
                        if should_click:
                            try:
                                opt.click()
                                print(f"    + Selected: {txt}")
                            except:
                                driver.execute_script("arguments[0].click();", opt)
                    
                    driver.find_element(By.TAG_NAME, 'body').click()
                    time.sleep(1)
                        
                except Exception as e:
                    print(f"  Error selecting categories: {e}")

            # ---------------------------------------------------------
            # 3. SET DATE FILTERS
            # ---------------------------------------------------------
            # CLEAR Published Date inputs first (for BOTH BO and AWD)
            print(f"  [DEBUG] Setting Dates: Start={start_date}, End={end_date}")
            print("  [DEBUG] Clearing Published Date inputs...")
            # Improved Clearing Logic with Stale Handling
            try:
                # Retry loop
                for _ in range(3):
                    try:
                        all_pickers = driver.find_elements(By.CSS_SELECTOR, "div.dateRangePicker_MAIN")
                        if not all_pickers: break
                        
                        pub_picker = all_pickers[0]
                        # Find clear buttons (X icon)
                        clears = pub_picker.find_elements(By.CSS_SELECTOR, 
                            "input[title='Reset'], input.datePicker_CLEAR-BUTTON, input.dateRangePicker_CLEAR-BUTTON, "
                            "input[title='Clear'], img[title='Clear'], input[alt='Clear'], "
                            "input.datePicker_CLEAR, input[value='X'], button[title='Clear'], "
                            "a[title='Clear'], a.datePicker_CLEAR"
                        )
                        
                        if not clears:
                            try:
                                clears = pub_picker.find_elements(By.XPATH, ".//*[@value='X' or text()='X' or @title='Clear' or @title='Reset']")
                            except: pass

                        if clears:
                             print(f"  [DEBUG] Found {len(clears)} potential 'Clear/Reset' buttons.")
                             for c in clears:
                                 if c.is_displayed():
                                     try:
                                         c.click()
                                         time.sleep(0.5)
                                     except:
                                         driver.execute_script("arguments[0].click();", c)
                                         time.sleep(0.5)
                             # Break if successful without stale
                             break 
                    except Exception as e:
                        if 'stale' in str(e).lower():
                            print("  [DEBUG] Stale element during clear. Retrying...")
                            time.sleep(1)
                            continue
                        else:
                            print(f"  [WARN] Clearing error: {e}")
                            break
                    
                # FORCE CLEAR via Keys on Inputs (Re-find to avoid stale)
                all_pickers = driver.find_elements(By.CSS_SELECTOR, "div.dateRangePicker_MAIN")
                if all_pickers:
                    pub_picker = all_pickers[0]
                    inputs = pub_picker.find_elements(By.CSS_SELECTOR, "input.datePicker_INPUT, input[type='text']")
                    for inp in inputs:
                        if inp.is_displayed():
                            try:
                                inp.click()
                                time.sleep(0.1)
                                inp.send_keys(Keys.CONTROL + "a")
                                inp.send_keys(Keys.DELETE)
                                driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", inp)
                            except: pass
                    print("  [DEBUG] Cleared Published Date fields.")
            except Exception as e:
                print(f"  [WARN] Failed to clear Published Date: {e}")

            target_label = "Published Date"
            if search_type == 'AWD':
                target_label = "Awarded Date"
                
            print(f"  [DEBUG] Target Date Label: {target_label}")
            
            # Strategy: Positional (User Requested: "Target the THIRD/LAST date range row")
            # We assume the order is: 1. Published Date, 2. Closed Date, 3. Awarded Date
            if search_type == 'AWD':
                 print(f"  [DEBUG] Using Positional Strategy: Targeting 3rd Date Row for '{target_label}'...")
                 
                 # FIRST DATE (Start)
                 try:
                     all_pickers = driver.find_elements(By.CSS_SELECTOR, "div.dateRangePicker_MAIN")
                     if len(all_pickers) >= 3:
                         target_picker = all_pickers[2]
                         icons = target_picker.find_elements(By.CSS_SELECTOR, "input[type='image'], img.ui-datepicker-trigger, input.datePicker_BUTTON")
                         if len(icons) >= 1:
                             print("  [DEBUG] Setting Start Date...")
                             # Ensure input is cleared first
                             try:
                                 inputs = target_picker.find_elements(By.CSS_SELECTOR, "input.datePicker_INPUT, input[type='text']")
                                 if inputs:
                                     inp = inputs[0]
                                     # Robust Clear: Click, Ctrl+A, Delete
                                     driver.execute_script("arguments[0].click();", inp)
                                     inp.send_keys(Keys.CONTROL + "a")
                                     inp.send_keys(Keys.DELETE)
                                     time.sleep(0.5)
                             except Exception as e:
                                 print(f"  [WARN] Failed manual clear of Start Date: {e}")

                             self._set_date_via_popup(driver, icons[0], start_date)
                             time.sleep(1) # Wait for JS updates
                     else:
                         print("  [WARN] Less than 3 date pickers found (Start Date).")
                 except Exception as e:
                     print(f"  [WARN] Error setting Start Date: {e}")

                 # SECOND DATE (End) - Re-find to avoid StaleElementReferenceException
                 try:
                     all_pickers = driver.find_elements(By.CSS_SELECTOR, "div.dateRangePicker_MAIN")
                     if len(all_pickers) >= 3:
                         target_picker = all_pickers[2]
                         icons = target_picker.find_elements(By.CSS_SELECTOR, "input[type='image'], img.ui-datepicker-trigger, input.datePicker_BUTTON")
                         if len(icons) >= 2:
                             print("  [DEBUG] Setting End Date...")
                             # Ensure input is cleared first
                             try:
                                 inputs = target_picker.find_elements(By.CSS_SELECTOR, "input.datePicker_INPUT, input[type='text']")
                                 if len(inputs) >= 2:
                                     inp = inputs[1]
                                     driver.execute_script("arguments[0].click();", inp)
                                     inp.send_keys(Keys.CONTROL + "a")
                                     inp.send_keys(Keys.DELETE)
                                     time.sleep(0.5)
                             except Exception as e:
                                 print(f"  [WARN] Failed manual clear of End Date: {e}")

                             self._set_date_via_popup(driver, icons[1], end_date)
                             time.sleep(1)
                         else:
                             print(f"  [WARN] Found target picker but only {len(icons)} icons (End Date). Needed 2.")
                     else:
                         print("  [WARN] Less than 3 date pickers found (End Date).")
                 except Exception as e:
                     print(f"  [WARN] Error setting End Date: {e}")
            
            else:
                # Normal logic (BO) - Switch to Positional (1st picker) for robustness
                # label_xpath = f"//*[contains(text(), '{target_label}')]/ancestor::tr[1]"
                # row_els = driver.find_elements(By.XPATH, label_xpath)
                try:
                    all_pickers = driver.find_elements(By.CSS_SELECTOR, "div.dateRangePicker_MAIN")
                    if all_pickers:
                         target_picker = all_pickers[0]
                         icons = target_picker.find_elements(By.CSS_SELECTOR, "input[type='image'], img.ui-datepicker-trigger, input.datePicker_BUTTON")
                         if len(icons) >= 2:
                             print("  [DEBUG] Setting Published Date (BO Normal) via Picker 0...")
                             # Set Start Date
                             self._set_date_via_popup(driver, icons[0], start_date)
                             time.sleep(1) # Wait for potential refresh
                             
                             # Verify Start Date
                             try:
                                 val = icons[0].find_element(By.XPATH, "./../input").get_attribute('value')
                                 print(f"  [DEBUG] Verified Start Date Input: {val}")
                             except: pass
                             
                             # Re-find keys for End Date (avoid stale)
                             all_pickers = driver.find_elements(By.CSS_SELECTOR, "div.dateRangePicker_MAIN")
                             if all_pickers:
                                 target_picker = all_pickers[0]
                                 icons = target_picker.find_elements(By.CSS_SELECTOR, "input[type='image'], img.ui-datepicker-trigger, input.datePicker_BUTTON")
                                 if len(icons) >= 2:
                                      self._set_date_via_popup(driver, icons[1], end_date)
                                 else:
                                     print(f"  [WARN] Picker 0 re-found but insufficient icons ({len(icons)}).")
                             else:
                                 print("  [WARN] Picker 0 lost during re-find.")
                         else:
                             print(f"  [WARN] Picker 0 found but insufficient icons ({len(icons)}).")
                    else:
                        print("  [WARN] Picker 0 not found for BO.")
                except Exception as e:
                    print(f"  [WARN] BO Date Set Error: {e}")
            
            # Skip the old block that relied on 'icons' being set
            icons = [] 

            # VERIFY INPUTS
            print("  [DEBUG] verifying date inputs before search...")
            try:
                # Re-find the target row based on search type logic
                if search_type == 'AWD':
                     # Positional (3rd picker)
                      all_pickers = driver.find_elements(By.CSS_SELECTOR, "div.dateRangePicker_MAIN")
                      if len(all_pickers) >= 3:
                          inputs = all_pickers[2].find_elements(By.CSS_SELECTOR, "input.datePicker_INPUT, input[type='text']")
                          if len(inputs) >= 2:
                              print(f"  [DEBUG] Awarded Date Input 1 logic value: {inputs[0].get_attribute('value')}")
                              print(f"  [DEBUG] Awarded Date Input 2 logic value: {inputs[1].get_attribute('value')}")
                else:
                     # BO (Published Date) - Use Positional (1st picker)
                     all_pickers = driver.find_elements(By.CSS_SELECTOR, "div.dateRangePicker_MAIN")
                     if all_pickers:
                         inputs = all_pickers[0].find_elements(By.CSS_SELECTOR, "input.datePicker_INPUT, input[type='text']")
                         if len(inputs) >= 2:
                              print(f"  [DEBUG] Published Date Input 1 logic value: {inputs[0].get_attribute('value')}")
                              print(f"  [DEBUG] Published Date Input 2 logic value: {inputs[1].get_attribute('value')}")
            except Exception as e:
                print(f"  [DEBUG] Verification failed: {e}")

            # ---------------------------------------------------------
            # 4. CLICK SEARCH
            # ---------------------------------------------------------
            # ---------------------------------------------------------
            # 4. CLICK SEARCH
            # ---------------------------------------------------------
            # Ensure popups are closed
            try:
                driver.find_element(By.TAG_NAME, 'body').click()
            except: pass
            time.sleep(1)

            print("  [DEBUG] Clicking Search...")
            search_clicked = False
            search_selectors = [
                 "//input[@value='Search']",
                 "//button[contains(.,'Search')]",
                 "//input[contains(@id, 'searchButton')]"
            ]
            
            for sel in search_selectors:
                btns = driver.find_elements(By.XPATH, sel)
                for btn in btns:
                    if btn.is_displayed():
                        try:
                            # Try scroll into view first
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(0.5)
                            btn.click()
                            search_clicked = True
                            break
                        except:
                            try:
                                driver.execute_script("arguments[0].click();", btn)
                                search_clicked = True
                                break
                            except: pass
                if search_clicked: break

            if not search_clicked:
                print("  [ERROR] Could not click Search button.")
                return []
            
            # Wait for search results
            time.sleep(3)
            
            # Check for "No opportunity found" early
            src = driver.page_source
            if "No opportunity found" in src or "No records found" in src:
                print("  [INFO] Search returned 'No opportunity found'. Checking if Closed tab exists explicitly...")
                # Sometimes it defaults to 'Open' (0) but 'Closed' has items?
                # But typically 'No opportunity found' means total 0.
                # However, let's proceed to tab check just in case, but warn.

            # ---------------------------------------------------------
            # 5. SWITCH TO 'CLOSED' TAB
            # ---------------------------------------------------------
            if search_type == 'AWD':
                print("  [DEBUG] Switching to 'Closed' tab for Awards...")

                
                # Increased retries to handle slow loading
                max_retries = 10 
                tab_clicked = False
                
                for _ in range(max_retries):
                    # Robust Selectors for "Closed" / "Awarded" Tab
                    tab_selectors = [
                        "//input[contains(@value, 'Closed')]",
                        "//button[contains(text(), 'Closed')]",
                        "//a[contains(text(), 'Closed')]",
                        "//span[contains(text(), 'Closed')]/ancestor::button",
                        "//input[contains(@value, 'Awarded')]"
                    ]
                    
                    found_tab_els = []
                    for sel in tab_selectors:
                        found_tab_els.extend(driver.find_elements(By.XPATH, sel))
                    
                    for t in found_tab_els:
                        if t.is_displayed():
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", t)
                                t.click()
                                tab_clicked = True
                                print("  [DEBUG] Clicked 'Closed' tab.")
                                time.sleep(5) 
                                break
                            except:
                                try:
                                    driver.execute_script("arguments[0].click();", t)
                                    tab_clicked = True
                                    print("  [DEBUG] Clicked 'Closed' tab (JS).")
                                    time.sleep(5)
                                    break
                                except: pass
                        if tab_clicked: break
                    
                    if tab_clicked: break
                    print("  [DEBUG] Waiting for 'Closed' tab...")
                    time.sleep(2)
                
                if not tab_clicked:
                    print("  [CRITICAL] Could not switch to 'Closed' tab. Aborting.")
                    return [] 
        
            # ---------------------------------------------------------
            # 6. PAGINATION & EXTRACTION
            # ---------------------------------------------------------
            page_num = 1
            while True:
                print(f"  Processing Result Page {page_num}...")
                
                src = driver.page_source
                if "No opportunity found" in src or "No records found" in src:
                    print("  No results found.")
                    break
                
                page_items, stop_signal_unused = self._extract_page_items(driver, start_date=None, end_date=None, search_type=search_type) 
                
                if search_type == 'AWD':
                    for pi in page_items:
                        pi['_is_award'] = True

                items.extend(page_items)
                print(f"    + Found {len(page_items)} items on this page.")
                
                if not page_items:
                    print("    (Empty page?)")
                
                try:
                    next_btn = None
                    selectors = [
                        "input[value='Next']",
                        "//input[@value='Next']",
                        "//button[contains(.,'Next')]"
                    ]
                    
                    for sel in selectors:
                        try:
                            if sel.startswith("//"):
                                el = driver.find_element(By.XPATH, sel)
                            else:
                                el = driver.find_element(By.CSS_SELECTOR, sel)
                            
                            if el.is_displayed():
                                next_btn = el
                                break
                        except: pass
                    
                    if next_btn and next_btn.is_enabled():
                        print("    Clicking Next Page...")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                        time.sleep(1)
                        try:
                            next_btn.click()
                        except:
                            driver.execute_script("arguments[0].click();", next_btn)
                        
                        time.sleep(5) 
                        page_num += 1
                    else:
                        print("  No next page.")
                        break
                except Exception as e:
                    print(f"  End of pagination (Error: {e}).")
                    break
        
        except Exception as e:
            print(f"GeBizClient Advanced Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            driver.quit()
        
        return items

    def _set_date_via_popup(self, driver, icon, date_obj):
        """Helper to set date using: Click Icon -> Clear -> Type -> Enter"""
        if not date_obj: return
        
        s_val = date_obj.strftime("%d%m%Y") # e.g. 05012024
        
        try:
            # 1. Try to find the INPUT relative to the icon (usually sibling or parent>sibling)
            # Structure: <div class="datePicker_MAIN"> <input class="datePicker_INPUT"> <input type="image"> ... </div>
            found_input = False
            try:
                # Try XPATH Sibling
                inputs = icon.find_elements(By.XPATH, "./preceding-sibling::input") + icon.find_elements(By.XPATH, "./following-sibling::input")
                # Filter for text/date inputs
                valid_inputs = [i for i in inputs if i.get_attribute('type') in ['text', '']]
                
                if valid_inputs:
                    inp = valid_inputs[0]
                    found_input = True
                    
                    # Manual Interaction
                    # Click to focus
                    driver.execute_script("arguments[0].click();", inp)
                    time.sleep(0.1)
                    
                    # Clear (Ctrl+A, Del)
                    inp.send_keys(Keys.CONTROL + "a")
                    inp.send_keys(Keys.DELETE)
                    time.sleep(0.1)
                    
                    # Type
                    inp.send_keys(s_val)
                    time.sleep(0.1)
                    
                    # Enter to confirm
                    inp.send_keys(Keys.ENTER)
                    return
            except Exception as e:
                print(f"  [WARN] Sibling input strategy failed: {e}")
            
            # 2. Fallback: Click Icon to open popup, then type in popup input
            print("  [DEBUG] Fallback to Popup Interaction...")
            driver.execute_script("arguments[0].click();", icon)
            time.sleep(0.5)

            popup_inputs = driver.find_elements(By.CSS_SELECTOR, "input.datePicker_CALENDAR-INPUT, input[placeholder='DDMMYYYY']")
            visible_pop = [p for p in popup_inputs if p.is_displayed()]
            
            if visible_pop:
                pop = visible_pop[0]
                pop.clear()
                pop.send_keys(s_val)
                
                # Set Button
                sets = driver.find_elements(By.CSS_SELECTOR, "input.datePicker_CALENDAR-BUTTON-SET, button.datePicker_CALENDAR-BUTTON-SET")
                visible_sets = [b for b in sets if b.is_displayed()]
                if visible_sets:
                    try:
                        visible_sets[0].click()
                    except:
                        driver.execute_script("arguments[0].click();", visible_sets[0])
                    time.sleep(1) 
        except Exception as e:
             print(f"  [WARN] Date Set Error: {e}")


    def fetch_opportunities(self, start_date=None, end_date=None):
        """Legacy Listing Fetcher (Simulated via Main Listing)"""
        # Kept for compatibility if needed, but app likely switches to fetch_advanced
        # Using the same _extract_page_items logic
        driver = self.setup_driver(headless=True)
        items = []
        try:
             driver.get("https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml?origin=opportunities")
             wait = WebDriverWait(driver, 20)
             # Search " " to reveal
             search_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Enter keywords']")))
             search_input.clear(); search_input.send_keys(" "); search_input.send_keys(Keys.ENTER)
             time.sleep(5)
             
             # Pagination
             while True:
                 stop_signal = False
                 page_items, stop = self._extract_page_items(driver, start_date, end_date, search_type=search_type)
                 items.extend(page_items)
                 if stop: break
                 
                 # Next
                 try:
                     nx = driver.find_element(By.CSS_SELECTOR, "input[value='Next']")
                     nx.click(); time.sleep(4)
                 except: break
        except: pass
        finally: driver.quit()
        return items

if __name__ == "__main__":
    # Test Advanced
    client = GeBizClient()
    # Mock category
    cats = ['Advertising Services']
    s = datetime(2025, 12, 1)
    e = datetime(2026, 1, 5)
    
    print("Testing Advanced Search...")
    res = client.fetch_advanced(start_date=s, end_date=e, categories=cats, search_type='BO')
    print(f"Result count: {len(res)}")
    for r in res[:3]:
        print(r)
