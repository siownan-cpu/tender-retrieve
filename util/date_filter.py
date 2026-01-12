from datetime import datetime, timedelta
from dateutil import parser
import pytz

def parse_date(date_str):
    try:
        # Detect ISO format (YYYY-MM-DD) vs DD/MM/YYYY
        # If it starts with YYYY (4 digits), assume ISO/Year-First
        if date_str and len(date_str) >= 4 and date_str[0:4].isdigit() and date_str[4] == '-':
             return parser.parse(date_str, dayfirst=False)
        return parser.parse(date_str, dayfirst=True)
    except:
        return None

def filter_by_date(items, mode='today', start_date=None, end_date=None, include_items_without_dates=False):
    """
    Filter items based on date range.
    
    Args:
        items: list of dicts with date fields
        mode: 'today', 'yesterday', 'last_3_days', 'last_7_days', 'last_24_hours', 'this_week', 'custom', 'specific_date'
        start_date: string 'YYYY-MM-DD' for custom mode
        end_date: string 'YYYY-MM-DD' for custom mode  
        include_items_without_dates: If True, include items without valid dates. Default False (exclude them).
    
    Returns:
        list: Filtered items
    """
    if not items:
        return []
        
    sg_tz = pytz.timezone('Asia/Singapore')
    now = datetime.now(sg_tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    cutoff = None
    end_cutoff = None
    
    if mode == 'today':
        # User implies 'Last 24 Hours' by the label 'Last 24 Hours (Today)'
        # So we use rolling 24h logic
        cutoff = now - timedelta(hours=24)
    elif mode == 'yesterday':
        cutoff = today_start - timedelta(days=1)
        end_cutoff = today_start - timedelta(seconds=1)
    elif mode == 'last_3_days':
        # User requested: start 1 day earlier for ranges
        # Originally 2 days back, now 3
        cutoff = today_start - timedelta(days=3)
    elif mode == 'last_7_days':
        # Originally 6, now 7
        cutoff = today_start - timedelta(days=7)
    elif mode == 'last_14_days':
        # Originally 13, now 14
        cutoff = today_start - timedelta(days=14)
    elif mode == 'last_31_days':
        # Originally 30, now 31
        cutoff = today_start - timedelta(days=31)
    elif mode == 'last_90_days':
        # Originally 89, now 90
        cutoff = today_start - timedelta(days=90)
    elif mode == 'last_365_days':
        # Originally 364, now 365
        cutoff = today_start - timedelta(days=365)
    elif mode == 'last_24_hours':
        # Strictly 24 hours back
        cutoff = now - timedelta(hours=24)
    elif mode == 'this_week':
        cutoff = today_start - timedelta(days=today_start.weekday())
    
    filtered = []
    items_without_dates = 0
    date_field_stats = {'Published Date': 0, 'Closing Date (fallback)': 0, 'Awarded Date': 0}
    
    for item in items:
        # For filtering by publication date:
        # 1. Try Published Date first (most accurate)
        # 2. If empty, use Closing Date as proxy (items must be published before closing)
        # 3. Don't use Date Detected (that's when WE detected it, not when it was published)
        
        pub_str = None
        used_field = None
        
        # Check Awarded Date first (if present, usually implies Award Search)
        awarded_date = item.get('Awarded Date') or item.get('awarded_date') or item.get('awarded_date_str')
        if awarded_date and str(awarded_date).strip():
             pub_str = awarded_date
             used_field = 'Awarded Date'
        else:
             # Check Published Date
             # Try Title Case (Normalized) then snake_case (Raw)
             published_date = item.get('Published Date') or item.get('published') or item.get('pub_date')
             if published_date and str(published_date).strip():  # Check for non-empty string
                 pub_str = published_date
                 used_field = 'Published Date'
             else:
                 # Fall back to Closing Date as a proxy
                 # Try Title Case (Normalized) then snake_case (Raw)
                 closing_date = item.get('Closing Date') or item.get('closing_date') or item.get('close_date')
                 if closing_date and str(closing_date).strip():
                     pub_str = closing_date
                     used_field = 'Closing Date (fallback)'
        
        # Handle items without any valid date fields
        if not pub_str:
            items_without_dates += 1
            if include_items_without_dates:
                filtered.append(item)
            continue
        
        # Track which field was used
        if used_field:
            date_field_stats[used_field] += 1
            
        # Try to parse the date
        pub_dt = parse_date(str(pub_str))
        if not pub_dt:
            items_without_dates += 1
            if include_items_without_dates:
                filtered.append(item)
            continue
            
        # Ensure timezone awareness
        if pub_dt.tzinfo is None:
            pub_dt = sg_tz.localize(pub_dt)
        else:
            pub_dt = pub_dt.astimezone(sg_tz)

        # Custom date range filtering
        if mode in ['custom', 'specific_date'] and start_date:
            try:
                # Start of start_date (00:00:00)
                s_dt = datetime.strptime(start_date, '%Y-%m-%d')
                s_dt = sg_tz.localize(s_dt.replace(hour=0, minute=0, second=0, microsecond=0))
                
                if pub_dt < s_dt:
                    continue
                
                # End of end_date (23:59:59)
                if end_date:
                    e_dt = datetime.strptime(end_date, '%Y-%m-%d')
                    e_dt = sg_tz.localize(e_dt.replace(hour=23, minute=59, second=59, microsecond=999999))
                    
                    if pub_dt > e_dt:
                        continue
                        
            except ValueError as e:
                print(f"⚠ Invalid date format: {e}")
                continue
        
        # Preset mode filtering
        elif cutoff:
            if pub_dt < cutoff:
                continue
            if end_cutoff and pub_dt > end_cutoff:
                continue
                 
        filtered.append(item)
    
    # Log summary
    if items_without_dates > 0:
        action = "included" if include_items_without_dates else "excluded"
        print(f"📊 Date Filter: {items_without_dates} items without valid dates were {action}")
    
    print(f"📊 Date Filter Results: {len(filtered)}/{len(items)} items passed the filter")
    
    # Show which date fields were used
    used_fields = {k: v for k, v in date_field_stats.items() if v > 0}
    if used_fields:
        print(f"📊 Date Fields Used: {used_fields}")
        
    return filtered
