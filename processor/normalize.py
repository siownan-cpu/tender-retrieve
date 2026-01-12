import re
from datetime import datetime
from dateutil import parser
import pytz
import yaml
from pathlib import Path

# Load feeds config to map URLs to categories
def load_feed_mapping():
    """Load feeds.yaml and create a mapping of feed URLs to main/sub categories"""
    cfg = Path('config/feeds.yaml')
    if not cfg.exists():
        return {}
    
    data = yaml.safe_load(cfg.read_text()) or {}
    feeds = data.get('feeds', {})
    
    # Create mapping: {feed_url: {'main': '...', 'sub': '...'}}
    url_mapping = {}
    for main_cat, subs in feeds.items():
        for sub_cat, types in subs.items():
            for feed_type, url in types.items():
                url_mapping[url] = {
                    'main': main_cat,
                    'sub': sub_cat
                }
    
    return url_mapping

# Load mapping once at module level
FEED_MAPPING = load_feed_mapping()

def extract_field(text, label):
    """Extract a field value from text using regex pattern"""
    if not text:
        return ''
    
    patterns = [
        rf'{label}[:\s]+([^\n\r]+?)(?:\s*\n|\s*$)',  # Match until newline or end
        rf'{label}[:\s]+(.+?)(?:Agency|Organisation|Closing|Published|Document|Quotation|Tender|$)',  # Match until next field
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            val = m.group(1)
            if val:  # Check if group(1) is not None
                val = val.strip()
                if val and val != ':':
                    return val
    return ''

def extract_tender_number(title, summary):
    """
    Extract ITQ or ITT number (merged into one field)
    
    Returns:
        str: The tender/quotation number found
    """
    combined_text = title + ' ' + summary
    
    # Try all patterns - ITQ, ITT, quotation, tender numbers
    patterns = [
        r'ITQ[:\s#]*([A-Z0-9\-/]{4,})',
        r'ITT[:\s#]*([A-Z0-9\-/]{4,})',
        r'Quotation No\.?[:\s#]*([A-Z0-9\-/]+)',
        r'Tender No\.?[:\s#]*([A-Z0-9\-/]+)',
        r'Document No\.?[:\s#]*([A-Z0-9\-/]+)',
        r'Doc\s*([0-9]{8,})', # Ariba Doc ID
        r'\b([0-9]{9,15})\b', # Ariba pure number ID (e.g. 1110001484)
        r'\b(Q[/-]?20\d{2}[/-]\d+)\b',
        r'\b(T[/-]?20\d{2}[/-]\d+)\b',
        r'\b([A-Z]{2,}\d{6,}[A-Z]{2,}\d{5,})\b',  # e.g., HDB000ETT25000296
    ]
    
    for pattern in patterns:
        m = re.search(pattern, combined_text, re.IGNORECASE)
        if m and m.group(1):
            return m.group(1).strip()
    
    return ''

def extract_date_only(date_str):
    """Parse date string and return only the date part (no time)"""
    if not date_str:
        return ''
    
    try:
        # Default to dayfirst=True for DD/MM/YYYY formats common in Singapore
        dt = parser.parse(date_str, dayfirst=True)
        # Convert to Singapore time if timezone-aware
        if dt.tzinfo:
            dt = dt.astimezone(pytz.timezone('Asia/Singapore'))
        
        return dt.strftime('%Y-%m-%d')
    except:
        return date_str

def extract_closing_info(summary):
    """Extract closing date and time from summary"""
    if not summary:
        return '', ''
    
    # Pattern: "Closing on 31/12/2024 23:59" or "Closing Date: 31-Dec-2024 5:00 PM"
    patterns = [
        r'Closing (?:on|Date)[:\s]+([0-9]{1,2}[/\-\s][A-Za-z0-9]{1,3}[/\-\s][0-9]{2,4})\s+([0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?(?:\s*[AP]M)?)',
        r'Closing (?:on|Date)[:\s]+([0-9]{1,2}[/\-\s][A-Za-z0-9]{1,3}[/\-\s][0-9]{2,4})',
    ]
    
    for pattern in patterns:
        m = re.search(pattern, summary, re.IGNORECASE)
        if m:
            closing_date = m.group(1) if m.group(1) else ''
            closing_time = m.group(2) if len(m.groups()) > 1 and m.group(2) else ''
            
            # Strip seconds only if seconds are present (e.g. 13:00:00 -> 13:00)
            # Check for 2 colons to avoid stripping minutes from 13:00
            if closing_time and closing_time.count(':') >= 2:
                # Remove last :ss part
                closing_time = re.sub(r':\d{2}(?=\s*[APap][Mm]|$)', '', closing_time)
                
            return closing_date, closing_time
    
    return '', ''

def extract_calling_entity(summary, title):
    """Extract calling entity/agency from summary or title"""
    if not summary and not title:
        return ''
    
    combined_text = summary + ' ' + title
    
    # Multiple patterns to catch various formats
    patterns = [
        # Pattern 1: Agency/Org name followed by pipe |
        r'(?:Agency|Organisation|Organization|Buyer|Calling Entity)[:\s]+([^|\n\r]+?)\s*\|',
        # Pattern 2: Agency/Org name followed by common delimiters
        r'(?:Agency|Organisation|Organization|Buyer|Calling Entity)[:\s]+([^|\n\r:]+?)(?:\s+(?:Document|Quotation|Tender|Supply|Delivery|Installation))',
        # Pattern 3: Agency/Org name ending with period or newline
        r'(?:Agency|Organisation|Organization)[:\s]+([A-Z][^|\n\r.]+?)(?:\.|,|\n|$)',
    ]
    
    for pattern in patterns:
        m = re.search(pattern, combined_text, re.IGNORECASE | re.MULTILINE)
        if m and m.group(1):
            entity = m.group(1).strip()
            
            # Additional safety: stop at first pipe if somehow captured
            if '|' in entity:
                entity = entity.split('|')[0].strip()
            
            # Stop at colon if it appears (but keep prefixes like "NUS:")
            parts = entity.split(':')
            if len(parts) > 1 and len(parts[0]) > 5:
                entity = parts[0].strip()
            
            # Clean up any remaining noise
            entity = re.sub(r'\s+(?:Document|Quotation|Tender|Supply|Delivery|Installation|Commissioning|ITQ|ITT).*$', '', entity, flags=re.IGNORECASE)
            
            # Validate length
            if entity and len(entity) > 3 and len(entity) < 100:  # Reasonable length
                return entity
    
    return ''

def get_category_from_url(feed_url):
    """
    Get main category and sub category from feed URL using the mapping
    
    Returns:
        tuple: (main_header, sub_header)
    """
    if not feed_url or feed_url == 'HTML_FALLBACK':
        return '', ''
    
    # Try to find in mapping
    if feed_url in FEED_MAPPING:
        return FEED_MAPPING[feed_url]['main'], FEED_MAPPING[feed_url]['sub']
    
    # Fallback: extract from URL if not in mapping
    match = re.search(r'/([^/]+)-CREATE_(?:BO|AWD)_FEED\.xml', feed_url)
    if match and match.group(1):
        sub_name = match.group(1).replace('_', ' ').replace(',', ', ')
        return '', sub_name  # No main category known
    
    return '', ''

print("DEBUG LOAD: processor.normalize loaded")

def normalize_items(items):
    """
    Normalize RSS feed items to required export format
    """
    norm = []
    
    for idx, item in enumerate(items, 1):
        title = item.get('title', '')
        summary = item.get('summary', '')
        link = item.get('link', '')
        
        # Normalize published date to YYYY-MM-DD to avoid ambiguity (MM/DD parsed as DD/MM)
        raw_pub = item.get('published', '')
        published = extract_date_only(raw_pub)
        
        feed_url = item.get('feed_url', '')
        source = item.get('source', 'rss')
        
        print(f"DEBUG ITEM: T='{title}' S='{source}'")
        
        # Skip if no title and no summary (ghost entry)
        if not title and not summary:
            print("  SKIP: No title/summary")
            continue
        
        # Skip if no meaningful title (less than 2 chars)
        if not title or len(title.strip()) < 2:
            continue
        
        feed_url = item.get('feed_url', '')
        source = item.get('source', 'rss')
        
        tender_number = None
        calling_entity = None
        sourcing_doc = None
        
        # Handle different sources
        if source == 'ariba':
            # SAP Ariba specific handling
            main_header = 'SAP Ariba - Singapore'
            
            # Sub Header -> Category or General (since Doc ID moved to own column)
            sub_header = item.get('category', 'General')
            
            # Sourcing Doc No
            sourcing_doc = item.get('doc_id', '')
            
            # ITQ/ITT -> RFI ID
            tender_number = item.get('rfi_id', '')
            
            # Category -> Product and Service Categories
            # (Already mapped to 'category' key by scraper, ensuring it flows to Category column)
            
            # Closing Date/Time
            # We captured close_date_raw with time in scraper
            if item.get('close_date_raw'):
                # Format: 13 Jan 2026 12:00 GMT+08:00
                raw = item.get('close_date_raw')
                try:
                    # Fuzzy parse to handle GMT offsets if needed, or split
                    dt = parser.parse(raw, fuzzy=True)
                    item['close_date'] = dt.strftime('%d %b %Y')
                    item['close_time'] = dt.strftime('%H:%M')
                    closing_time = dt.strftime('%H:%M')
                except:
                    pass
            
            # Buyer/Company -> Calling Entity
            calling_entity = item.get('buyer', 'SAP Ariba')
        elif source == 'sesami':
            # Sesami specific handling
            main_header = 'Sesami Business Opportunities'
            sub_header = item.get('category', 'General')
        elif source == 'SIT':
            main_header = 'SIT Procurement Opportunities'
            sub_header = item.get('category', 'General')
            # Custom mappings for SIT
            tender_number = item.get('ref_no', '')
            if not tender_number:
                tender_number = extract_tender_number(title, summary)
            calling_entity = 'Singapore Institute of Technology'
            
        elif source == 'JPMC Brunei':
            main_header = 'JPMC Brunei Tenders'
            sub_header = item.get('category', 'General')
            # Custom mappings for JPMC
            tender_number = item.get('ref_no', '')
            calling_entity = 'Jerudong Park Medical Centre'
            
            # Force Published Date to today to bypass date filtering
            # as requested by user ("ignore date filtering... fetch everything... as long as current")
            # This ensures it passes "Last 24 hours" filter in app_enhanced.py
            published = datetime.now().strftime('%d %b %Y') # e.g. 01 Jan 2026

        elif source == 'TenderBoard':
            main_header = 'TenderBoard Opportunities'
            # Use Industry as Sub Header
            sub_header = item.get('industry') or item.get('category', 'General')
            if not sub_header:
                 sub_header = 'General'
            
            # Custom mappings for TenderBoard
            tender_number = item.get('ref_no')
            calling_entity = item.get('buyer', 'TenderBoard')
            
            # Special Handling for SIT
            if calling_entity and "SINGAPORE INSTITUTE OF TECHNOLOGY" in calling_entity.upper():
                # Extract Ref No from Title (e.g. TO2025019)
                if not tender_number:
                    m = re.search(r'(TO\d+[A-Za-z]?)', title)
                    if m:
                        tender_number = m.group(1)
                
                # Extract Dates from Title/Summary if missing
                if not item.get('close_date'):
                    matches = re.findall(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', title)
                    if matches:
                         item['close_date'] = matches[-1]

        elif source.startswith('ST Logistics'):
            main_header = 'ST Logistics Business Opportunities'
            sub_header = item.get('category', 'General')
            
            # Map ST Logistics specific fields
            tender_number = item.get('ref_no', '')
            calling_entity = 'ST Logistics'
            
            # Handle closing date from stlogs_client output
            if item.get('closing_date'):
                item['close_date'] = item.get('closing_date')

        elif source == 'gebiz_selenium':
            cat = item.get('category', 'Business Opportunities')
            
            # Check for "Main ⇒ Sub" pattern (common in text)
            if '⇒' in cat:
                parts = cat.split('⇒')
                main_part = parts[0].strip()
                sub_part = parts[1].strip()
                main_header = f"GEBIZ - {main_part}"
                sub_header = sub_part
            else:
                main_header = f"GEBIZ - {cat}"
                sub_header = cat
            
            # Map captured fields
            tender_number = item.get('document_no')
            calling_entity = item.get('agency')
            
            # Map closing date string for later extraction/parsing
            if item.get('closing_date_str'):
                item['closing_date'] = item.get('closing_date_str')
            
        else:
            # GeBIZ handling (RSS)
            # Get main category and sub category from feed URL mapping
            main_header, sub_header = get_category_from_url(feed_url)
            
            # Skip if no main header (shouldn't happen but safety check)
            if not main_header:
                continue
            
            # Prepend "GEBIZ - " to Main Header
            main_header = f"GEBIZ - {main_header}"
            
            # For GeBIZ/Aruba/Sesami, extraction happens later
            tender_number = None
            calling_entity = None
        
        # Map specific client keys to standard keys
        if item.get('pub_date'):
            published = item.get('pub_date')
        elif item.get('publish_date_str'):
            published = item.get('publish_date_str')
        
        # Extract published date (no time)
        # BUG FIX: processing ST Logistics YYYY-MM-DD with extract_date_only(dayfirst=True) caused date swap.
        # Bypass re-parsing if source is ST Logistics and it looks like YYYY-MM-DD
        if source.startswith('ST Logistics') and re.match(r'^\d{4}-\d{2}-\d{2}', str(published)):
            published_date = str(published).split(' ')[0] # Keep YYYY-MM-DD part, ignore time if present
        else:
            published_date = extract_date_only(published)
        
        # If no published date from RSS, try to extract from summary/title
        if not published_date:
            # Try to find date patterns in summary
            date_patterns = [
                r'(?:Published|Posted|Date)[:\s]+([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})',
                r'([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4})',
            ]
            for pattern in date_patterns:
                m = re.search(pattern, summary, re.IGNORECASE)
                if m and m.group(1):
                    published_date = m.group(1)
                    break
        
        # Extract closing date and time
        if item.get('close_date'):
            closing_date_raw = item.get('close_date')
            closing_time = str(item.get('close_time', '')) # Future proofing
        else:
            closing_date_raw, closing_time = extract_closing_info(summary)
            
        # Ensure Closing Time is HH:MM (strip seconds)
        if closing_time and closing_time.count(':') >= 2:
             closing_time = re.sub(r':\d{2}(?=\s*[APap][Mm]|$)', '', closing_time)
        
        # Normalize closing date for comparison and export
        closing_date = extract_date_only(closing_date_raw) if closing_date_raw else ''
        
        # GeBIZ RSS often sets pubDate to Closing Date. Detecting this error:
        if published_date and closing_date and published_date == closing_date:
            published_date = ''
            
        # Extract ITQ/ITT number (merged)
        if not tender_number:
            tender_number = item.get('itq_itt') or extract_tender_number(title, summary)
        
        # Extract calling entity (improved extraction)
        if not calling_entity:
            calling_entity = item.get('calling_entity') or extract_calling_entity(summary, title)
        
        # Closing Date override
        if item.get('closing_date'):
            closing_date = extract_date_only(item.get('closing_date'))
            # If closing_date has a time part like "17:00", strict date extraction might lose it if looking for date only.
            # But the export separates Date and Time.
            # Sesami "14 Jan 2026 17:00". extract_date_only handles the date.
            # We need time too.
            cd_raw = item.get('closing_date')
            try:
                dt_close = parser.parse(cd_raw)
                closing_time = dt_close.strftime('%H:%M')
            except:
                pass

        # Date detected
        date_detected = datetime.now().strftime('%Y-%m-%d')
        
        # Description
        description = title
        
        # New columns from Ariba
        category_val = item.get('category', '')
        # Only populate Category column if explicitly requested or relevant
        # But user asked for "another column for category at the end"
        
        opp_amount = item.get('opportunity_amount', '')
        
        # Determine if this is an Award (for separation in Excel)
        is_award = item.get('_is_award', False)
        if not is_award:
            if source == 'rss' and '_AWD_' in feed_url:
                is_award = True
            elif source == 'gebiz_selenium' and item.get('search_type') == 'AWD':
                is_award = True
        
        awarded_date = item.get('awarded_date_str', '')
        awarded_to = item.get('awarded_to', '')
        award_value = item.get('award_value', '')
        
        norm.append({
            'No.': idx,
            'Published Date': published_date,
            'Awarded Date': awarded_date,
            'awarded_to': awarded_to,
            'award_value': award_value,
            '_is_award': is_award,
            'Closing Date': closing_date,
            'Closing Time': closing_time,
            'Date Detected': date_detected,
            'ITQ/ITT': tender_number,
            'Calling Entity': calling_entity,
            'Description': description,
            'Link': link,
            #'_is_award': is_award, # Removed duplicate
            'Main Header': main_header,
            'Sub Header': sub_header,
            'Sourcing Doc No.': sourcing_doc,
            'Opportunity Amount': opp_amount
        })
    
    # Renumber after filtering
    for idx, item in enumerate(norm, 1):
        item['No.'] = idx
    
    return norm
