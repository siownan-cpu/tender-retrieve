import os
import json
import time
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, send_file, jsonify, redirect, url_for
from dotenv import load_dotenv

from collector.rss_client import fetch_feeds, load_feeds_config
from collector.ariba_client import fetch_ariba_opportunities
from collector.sesami_client import fetch_sesami_opportunities
from collector.tenderboard_client import TenderBoardClient
from collector.stlogs_client import STLogsClient
from collector.jpmc_client import JPMCClient
from collector.gebiz_client import GeBizClient
from collector.html_fallback import fetch_today_opportunities
from processor.normalize import normalize_items
from exporter.excel import export_to_excel
from util.date_filter import filter_by_date
from util.selection_manager import save_selection, load_selection, list_selections, delete_selection
from util.gebiz_helper import categorize_selected_urls

load_dotenv()

app = Flask(__name__)
cache_items = []
cache_metadata = None

@app.route('/')
def index():
    feeds = load_feeds_config()
    return render_template_string(TEMPLATE, feeds=feeds, count=None, ts=None, download_ready=False)

@app.route('/fetch', methods=['GET', 'POST'])
def fetch():
    if request.method == 'GET':
        return redirect(url_for('index'))
    selected_urls = request.form.getlist('feed_url')
    use_html = request.form.get('use_html') == '1'
    use_ariba = request.form.get('use_ariba') == '1'
    date_mode = request.form.get('date_mode', 'today')
    date_start = request.form.get('date_start')
    date_end = request.form.get('date_end')
    use_sesami = request.form.get('use_sesami') == '1'
    
    # Safe JSON access
    json_data = request.get_json(silent=True) or {}
    
    if not selected_urls and json_data:
        selected_urls = json_data.get('feed_url', [])
        
    force_rss = request.form.get('force_rss') == '1' or json_data.get('force_rss') == True
    
    print("\n" + "="*80)
    print("FETCH REQUEST RECEIVED")
    print("="*80)
    print(f"Date Mode (raw): {date_mode}")
    print(f"Date Start: {date_start}")
    print(f"Date End: {date_end}")
    print(f"Selected URLs: {len(selected_urls)}")
    print(f"Use Ariba: {use_ariba}")
    print(f"Use Sesami: {use_sesami}")
    print(f"Force RSS: {force_rss}")
    print("="*80 + "\n")

    # Calculate effective dates for export naming
    # Calculate effective dates for export naming
    e_start = datetime.now()
    e_end = datetime.now()
    try:
        if date_start:
            e_start = datetime.strptime(date_start, '%Y-%m-%d')
        
        if date_end:
            e_end = datetime.strptime(date_end, '%Y-%m-%d')
        else:
            # Fallbacks if no explicit end date
            if date_mode == 'today' or date_mode == 'last_24_hours': 
                e_end = datetime.now()
                e_start = e_end - timedelta(days=1)
            elif date_mode == 'last_working_day':
                 # Keep e_end as now or calculated?
                 # If date_start was passed (from UI calc), use it as both start/end (single day export)
                 # UNLESS user wants range.
                 # Actually, usually LWD is single day. 
                 # But if user customized it...
                 if not date_start: # Auto-calc
                     now = datetime.now()
                     wd = now.weekday()
                     if wd == 0: e_start = now - timedelta(days=3)
                     elif wd == 6: e_start = now - timedelta(days=2)
                     else: e_start = now - timedelta(days=1)
                     e_end = now # Include today (User Request: "until today inclusive")
            elif date_mode == 'last_7_days': e_start = datetime.now() - timedelta(days=7)
            # ... other presets rely on e_end = now (default)
            
    except Exception as e:
        print(f"Error parsing dates for export name: {e}")
        
    app.config['export_date_start'] = e_start
    app.config['export_date_end'] = e_end

    preset_modes = ['last_working_day', 'today', 'last_7_days', 'last_14_days', 'last_31_days', 'last_90_days', 'last_365_days']
    if date_mode == 'specific_date' and date_start:
        # Treat as single day
        date_end = date_start
        date_mode = 'custom'
        print(f"→ Adjusted to custom mode: {date_start} to {date_end}")
    elif date_start and date_mode not in preset_modes: 
        # Only force custom if it's not a known preset
        date_mode = 'custom'
        print(f"→ Using custom date range: {date_start} to {date_end or 'now'}")
    
    items = []
    
    
    special_tokens = ['ENABLE_TENDERBOARD', 'ENABLE_JPMC', 'ENABLE_STLOGS', 'ENABLE_SESAMI']
    scraper_urls = [u for u in selected_urls if u in special_tokens]
    rss_candidate_urls = [u for u in selected_urls if u not in special_tokens]

    # Fetch GeBIZ feeds (with date filtering at source)
    if rss_candidate_urls:
         # Determine if we should use Selenium for GeBIZ (Historical Data)
         use_selenium_gebiz = False
         if date_mode not in ['today', 'last_24_hours']:
             use_selenium_gebiz = True
             
         gebiz_urls = [u for u in rss_candidate_urls if 'gebiz.gov.sg' in u or '_FEED.xml' in u]
         other_urls = [u for u in rss_candidate_urls if 'gebiz.gov.sg' not in u]
         
         # Split GeBIZ URLs into BO and AWD based on pattern
         gebiz_awd_urls = [u for u in gebiz_urls if '_AWD_FEED' in u or 'AWD' in u] # Simple heuristic for routing
         gebiz_bo_urls = [u for u in gebiz_urls if u not in gebiz_awd_urls]
         
         # Logic:
         # 1. AWD: ALWAYS use Selenium (User requirement)
         # 2. BO: Use Selenium only if historical (not today/24h)
         use_selenium_bo = date_mode not in ['today', 'last_24_hours']
         
         selenium_target_urls = gebiz_awd_urls + (gebiz_bo_urls if use_selenium_bo else [])
         rss_gebiz_urls = (gebiz_bo_urls if not use_selenium_bo else [])
         
         # 1. Fetch RSS (Non-GeBIZ + GeBIZ BO if applicable)
         rss_fetch_urls = other_urls + rss_gebiz_urls
         
         if rss_fetch_urls:
             print(f"Fetching {len(rss_fetch_urls)} feeds via RSS (Fast Mode)...")
             items += fetch_feeds(selected_urls=rss_fetch_urls, date_mode=date_mode, 
                                start_date=date_start, end_date=date_end)
                                
         # 2. Fetch GeBIZ Historical/Awards Data (Selenium Advanced Search)
         if selenium_target_urls:
              try:
                  print("\n🌐 Fetching GeBIZ Historical Data (Selenium Advanced Search)...")
                  
                  # Calculate dates for client
                  c_start = datetime.now()
                  c_end = datetime.now() # Default end to now
                  
                  now = datetime.now()
                  if date_mode == 'last_7_days': c_start = now - timedelta(days=7)
                  elif date_mode == 'last_14_days': c_start = now - timedelta(days=14)
                  elif date_mode == 'last_31_days': c_start = now - timedelta(days=31)
                  elif date_mode == 'last_90_days': c_start = now - timedelta(days=90)
                  elif date_mode == 'last_365_days': c_start = now - timedelta(days=365)
                  elif date_mode == 'custom' and date_start:
                       try:
                           c_start = datetime.strptime(date_start, '%Y-%m-%d')
                           if date_end: c_end = datetime.strptime(date_end, '%Y-%m-%d')
                       except Exception as e:
                           print(f"Error parsing date strings: {e}")
                  elif date_mode == 'last_working_day':
                      c_start = app.config['export_date_start']
                      c_end = app.config['export_date_end']
                  
                  # Helper to categorize URLs
                  print(f"  [DEBUG] Selected URLs (Total {len(selenium_target_urls)}): {selenium_target_urls[:3]}...")
                  cat_map = categorize_selected_urls(selenium_target_urls)
                  print(f"  [DEBUG] Category Map: BO={len(cat_map['BO'])}, AWD={len(cat_map['AWD'])}")
                  if cat_map['AWD']: print(f"  [DEBUG] AWD Categories: {cat_map['AWD']}")
                  # cat_map = {'BO': [...], 'AWD': [...]}
                  
                  gb_client = GeBizClient()
                  
                  # Fetch BO
                  if cat_map['BO']:
                      print(f"  > Searching Business Opportunities ({len(cat_map['BO'])} categories)...")
                      gb_items_bo = gb_client.fetch_advanced(
                          start_date=c_start, 
                          end_date=c_end, 
                          categories=cat_map['BO'],
                          search_type='BO'
                      )
                      items += gb_items_bo
                      
                  # Fetch AWD
                  if cat_map['AWD']:
                      print(f"  > Searching Awards ({len(cat_map['AWD'])} categories)...")
                      gb_items_awd = gb_client.fetch_advanced(
                          start_date=c_start, 
                          end_date=c_end,
                          categories=cat_map['AWD'],
                          search_type='AWD'
                      )
                      items += gb_items_awd

                  print(f"✓ Added GeBIZ Selenium opportunities")
              except Exception as e:
                  print(f"❌ GeBIZ Selenium fetch failed: {e}")
                  import traceback
                  traceback.print_exc()
    
    # Fetch SAP Ariba feeds (automated)
    if use_ariba:
        print("\n🌐 Fetching SAP Ariba opportunities...")
        # Map 'last_working_day' to 'custom' for Ariba if not effectively handled
        ariba_date_mode = date_mode
        ariba_start_date = date_start
        ariba_end_date = date_end
        if date_mode == 'last_working_day':
            # ariba_date_mode = 'custom' # Removed override: Let client map this to 'Last 7 days'
            # Update: Ariba V2 maps 'last_working_day' -> 'Last 7 days' internally.
            # We explicitly pass dates for post-filtering, but Ariba fetcher uses mode.
            ariba_start_date = app.config['export_date_start'].strftime('%Y-%m-%d')
            ariba_end_date = app.config['export_date_end'].strftime('%Y-%m-%d')
        elif date_start:
             # Ensure Ariba sees this as custom if dates are present but mode isn't preset
             ariba_date_mode = 'custom'
             ariba_start_date = date_start
             ariba_end_date = date_end

        # Ariba Pages Limit
        ariba_pages = request.form.get('ariba_pages', '10')
        if ariba_pages == 'custom':
            ariba_pages = request.form.get('ariba_pages_custom', '10')
        
        try:
            ariba_max_pages = int(ariba_pages)
        except:
            ariba_max_pages = 10

        # Run Ariba in headless mode (Background)
        print(f"Fetching Ariba (Headless Mode, Max {ariba_max_pages} pages)...")
        ariba_items = fetch_ariba_opportunities(
            headless=True, 
            date_mode=ariba_date_mode, 
            date_start=ariba_start_date, 
            date_end=ariba_end_date,
            max_pages=ariba_max_pages
        )
        
        # Pre-process Ariba items for date filtering
        # Ariba v2 returns 'published' as "Closing: dd Mon yyyy"
        # We want to put this into a format that date_filter might parse, or at least ensure parsing works.
        # However, date_filter looks for 'Published Date' or 'Closing Date'.
        # normalize_items() will likely map 'published' -> 'Published Date'.
        # Let's clean it up here or rely on normalize. 
        # Actually normalize_items likely just copies fields.
        # Let's clean the string so dateutil.parser can handle it.
        for item in ariba_items:
            pub = item.get('published', '')
            if pub.startswith('Closing: '):
                # Clean date string "09 Jan 2026"
                raw_date = pub.replace('Closing: ', '').strip()
                
                # Map to 'close_date' so normalize.py populates 'Closing Date' column
                item['close_date'] = raw_date
                
                # Handling Published Date logic
                # User request: "if we use the date filter as Last 24 hours (today), then you can use today's date as the Published Date"
                # Otherwise, clear it so it doesn't confuse filtering/logic (default Ariba behavior).
            if ariba_date_mode in ['today', 'last_24_hours']:
                 item['published'] = datetime.now().strftime('%d %b %Y')
            else:
                # Use today's date so items pass through date filter
                item['published'] = datetime.now().strftime('%Y-%m-%d') 
            
            # Ensure Source is set (it is in scraper but good to be sure)
            item['source'] = 'ariba'

        items += ariba_items
        print(f"✓ Added {len(ariba_items)} Ariba opportunities")
        
    # Capture use flags before removing from list (Fixes metadata False issue)
    use_stlogs = 'ENABLE_STLOGS' in selected_urls
    use_tenderboard = 'ENABLE_TENDERBOARD' in selected_urls
    use_jpmc = 'ENABLE_JPMC' in selected_urls

    # Fetch Sesami opportunities
    if 'ENABLE_SESAMI' in selected_urls:
        use_sesami = True
        selected_urls.remove('ENABLE_SESAMI')
        
    if use_sesami:
        print("\n🌐 Fetching Sesami opportunities...")
        
        # Map date_mode to Sesami's expected format
        s_date_mode = date_mode
        s_start = None
        s_end = None
        s_custom_days = None

        if date_mode in ['today', 'last_24_hours']:
            s_date_mode = '24h'
        elif date_mode == 'last_7_days':
            s_date_mode = '7days'
        elif date_mode == 'last_14_days':
            s_date_mode = 'custom'
            s_custom_days = 14
        elif date_mode == 'last_31_days':
            s_date_mode = 'custom'
            s_custom_days = 31
        elif date_mode == 'last_90_days':
            s_date_mode = 'custom'
            s_custom_days = 90
        elif date_mode == 'last_365_days':
            s_date_mode = 'custom'
            s_custom_days = 365
        elif date_mode == 'last_working_day':
             s_date_mode = 'custom'
             s_start = app.config['export_date_start']
             s_end = app.config['export_date_end']
        elif date_mode in ['custom', 'specific_date'] or date_start:
            s_date_mode = 'custom'
            try:
                 if date_start: s_start = datetime.strptime(date_start, '%Y-%m-%d')
                 if date_end: s_end = datetime.strptime(date_end, '%Y-%m-%d')
            except: pass
        
        try:
            # Correct function call (NOT class instantiation)
            # Fetch Sesami opportunities
            # Signature: fetch_sesami_opportunities(headless=True, date_mode='24h', custom_days=None, start_date=None, end_date=None)
            
            s_start_str = s_start.strftime('%Y-%m-%d') if s_start else None
            s_end_str = s_end.strftime('%Y-%m-%d') if s_end else None
            
            sesami_items = fetch_sesami_opportunities(
                headless=True, 
                date_mode=s_date_mode,
                custom_days=s_custom_days,
                start_date=s_start_str,
                end_date=s_end_str
            )
                
            items += sesami_items
            print(f"✓ Added {len(sesami_items)} Sesami opportunities")
        except Exception as e:
            print(f"❌ Sesami fetch failed: {e}")
            import traceback
            traceback.print_exc()

    # Fetch ST Logistics opportunities
    if use_stlogs:
        if 'ENABLE_STLOGS' in selected_urls: selected_urls.remove('ENABLE_STLOGS')
    # Fetch TenderBoard opportunities
    if use_tenderboard:
         if 'ENABLE_TENDERBOARD' in selected_urls: selected_urls.remove('ENABLE_TENDERBOARD')
         print("\n🌐 Fetching TenderBoard opportunities...")
         # TODO: Implement full TenderBoard call if needed, similar to above.
         # For now, we assume user might trigger it via other means or separate loop?
         # But based on prev code, it seemed to be a placeholder or separate flow.
         pass
    
    if use_jpmc:
         print("\n🌐 Fetching JPMC opportunities...")
         try:
             jpmc_client = JPMCClient()
             jpmc_items = jpmc_client.fetch_opportunities(date_mode=date_mode, start_date=e_start, end_date=e_end)
             items += jpmc_items
             print(f"✓ Added {len(jpmc_items)} JPMC opportunities")
         except Exception as e:
             print(f"❌ JPMC fetch failed: {e}")
             import traceback
             traceback.print_exc()

    if use_tenderboard:
        print("\n🌐 Fetching TenderBoard opportunities...")
        try:
            tb_client = TenderBoardClient()
            tb_items = tb_client.fetch_opportunities(start_date=e_start, end_date=e_end)
            items += tb_items
            print(f"✓ Added {len(tb_items)} TenderBoard opportunities")
        except Exception as e:
            print(f"❌ TenderBoard fetch failed: {e}")
            import traceback
            traceback.print_exc()

    if use_stlogs:
         print("\n🌐 Fetching ST Logistics opportunities...")
         try:
             # Prefer explicit dates from request if available
             st_start, st_end = e_start, e_end
             if date_start:
                 try:
                     st_start = datetime.strptime(date_start, '%Y-%m-%d')
                     if date_end: 
                         st_end = datetime.strptime(date_end, '%Y-%m-%d')
                     else:
                         st_end = datetime.now() # Default end to now
                 except: pass

             st_client = STLogsClient()
             # If we have specific dates, pretend mode is custom/specific so client logic holds
             st_mode = date_mode
             if date_start: st_mode = 'custom'
             
             st_items = st_client.fetch_opportunities(date_mode=st_mode, start_date=st_start, end_date=st_end)
             items += st_items
             print(f"✓ Added {len(st_items)} ST Logistics opportunities")
         except Exception as e:
             print(f"❌ ST Logistics fetch failed: {e}")
             import traceback
             traceback.print_exc()

    # Fetch HTML fallback
    if use_html:
        items += fetch_today_opportunities()
        
    # Post-processing
    print(f"DEBUG: Total Raw Items Fetched: {len(items)}")
    
    norm_items = normalize_items(items)
    print(f"DEBUG: Normalized Items: {len(norm_items)}")
    
    # Two-stage date filtering:
    # 1. RSS-level: rss_client.py filters GeBIZ items by 'published' date from RSS
    # 2. Post-filter: date_filter.py does final filtering after normalization
    
    # Force 'custom' mode if explicit dates are provided, to ensure date_filter respects strict range
    filter_mode = date_mode
    if date_start:
        filter_mode = 'custom'
        
    filtered_items = filter_by_date(norm_items, mode=filter_mode, start_date=date_start, end_date=date_end,
                                   include_items_without_dates=True)
                                   
    print(f"DEBUG: Final Filtered Items: {len(filtered_items)}")
    if len(items) > 0 and len(filtered_items) == 0:
        print("DEBUG WARNING: All items were filtered out! Check date parsing.")
        # Print sample date from raw items
        if 'published_date' in items[0]:
            print(f"  Sample Raw Date: {items[0]['published_date']} (Type: {type(items[0]['published_date'])})")
    
    global cache_items
    cache_items = filtered_items
    
    # Store metadata for export
    # Format feeds list with newlines for better Excel display
    feeds_list_str = "\n".join([u.split('/')[-1] for u in selected_urls]) if selected_urls else 'None'
    
    global cache_metadata
    cache_metadata = {
        'Export Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'Date Mode': date_mode,
        'Start Date': date_start,
        'End Date': date_end,
        'Use Ariba': f"{use_ariba}" + (f" (Pages: {request.form.get('ariba_pages', '10')})" if use_ariba else ""),
        'Use Sesami': use_sesami,
        'Use TenderBoard': use_tenderboard,
        'Use ST Logistics': use_stlogs,
        'Use JPMC': use_jpmc,
        'Selected Feeds Count': len(selected_urls),
        'Selected Feeds': feeds_list_str
    }
    
    feeds = load_feeds_config()
    return render_template_string(TEMPLATE, feeds=feeds, count=len(cache_items), 
                                ts=datetime.now().strftime('%Y-%m-%d %H:%M'), 
                                date_mode=date_mode, download_ready=False)

@app.route('/export', methods=['POST'])
def export():
    output_dir = 'output'
    
    # Generate filename
    s_date = app.config.get('export_date_start', datetime.now())
    e_date = app.config.get('export_date_end', datetime.now())
    fmt = "%y%m%d"
    export_file = f"{s_date.strftime(fmt)}-{e_date.strftime(fmt)} Tender Export.xlsx"
    
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, export_file)
    export_to_excel(cache_items, path, metadata=cache_metadata)
    
    app.config['last_export'] = path
    feeds = load_feeds_config()
    return render_template_string(TEMPLATE, feeds=feeds, count=len(cache_items), 
                                ts=datetime.now().strftime('%Y-%m-%d %H:%M'), 
                                date_mode='exported', download_ready=True,
                                export_filename=export_file)

@app.route('/download')
def download():
    path = app.config.get('last_export')
    if not path:
        return 'No file', 404
    return send_file(path, as_attachment=True)

@app.route('/selections/list', methods=['GET'])
def selections_list():
    """Return list of saved selections"""
    selections = list_selections()
    return jsonify(selections)

@app.route('/selections/save', methods=['POST'])
def selections_save():
    """Save current selection"""
    data = request.get_json()
    name = data.get('name')
    feed_type = data.get('feed_type')
    selected_feeds = data.get('selected_feeds', [])
    
    if not name:
        return jsonify({'success': False, 'message': 'Selection name required'}), 400
    
    success, message = save_selection(name, feed_type, selected_feeds)
    return jsonify({'success': success, 'message': message})

@app.route('/selections/load/<name>', methods=['GET'])
def selections_load(name):
    """Load a selection"""
    selection = load_selection(name)
    if not selection:
        return jsonify({'success': False, 'message': 'Selection not found'}), 404
    return jsonify({'success': True, 'selection': selection})

@app.route('/selections/delete/<name>', methods=['DELETE'])
def selections_delete(name):
    """Delete a selection"""
    success, message = delete_selection(name)
    return jsonify({'success': success, 'message': message})

TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GeBIZ RSS Feed Manager</title>
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 0;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }
        
        h1 {
            margin: 0 0 10px 0;
            color: #1f2937;
            font-size: 32px;
            font-weight: 700;
        }
        
        .subtitle {
            color: #6b7280;
            font-size: 16px;
        }
        
        .main-content {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
        }
        
        .card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .card-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            font-weight: 600;
            font-size: 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .card-body {
            padding: 25px;
        }
        
        /* Feed Type Tabs */
        .feed-type-tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 25px;
            padding: 5px;
            background: #f3f4f6;
            border-radius: 8px;
        }
        
        .feed-type-tab {
            flex: 1;
            padding: 12px 20px;
            background: white;
            border: 2px solid transparent;
            border-radius: 6px;
            cursor: pointer;
            text-align: center;
            font-weight: 600;
            transition: all 0.3s;
        }
        
        .feed-type-tab:hover {
            border-color: #667eea;
        }
        
        .feed-type-tab.active {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }
        
        .feed-type-content {
            display: none;
        }
        
        .feed-type-content.active {
            display: block;
        }
        
        /* Category Selection */
        .category-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .category-card {
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            overflow: hidden;
            transition: all 0.3s;
        }
        
        .category-card:hover {
            border-color: #667eea;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
        }
        
        .category-header {
            background: #f9fafb;
            padding: 12px 15px;
            font-weight: 600;
            color: #1f2937;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            user-select: none;
        }
        
        .category-header:hover {
            background: #f3f4f6;
        }
        
        .category-count {
            background: #667eea;
            color: white;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .category-body {
            padding: 15px;
            background: white;
            display: none;
        }
        
        .category-body.expanded {
            display: block;
        }
        
        .subcategory-item {
            display: flex;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #f3f4f6;
        }
        
        .subcategory-item:last-child {
            border-bottom: none;
        }
        
        .subcategory-item input[type="checkbox"] {
            margin-right: 10px;
            width: 18px;
            height: 18px;
            cursor: pointer;
        }
        
        .subcategory-item label {
            flex: 1;
            cursor: pointer;
            font-size: 14px;
            color: #374151;
        }
        
        /* Controls */
        .controls {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }
        
        .control-group {
            flex: 1;
            min-width: 200px;
        }
        
        .control-group label {
            display: block;
            font-weight: 600;
            margin-bottom: 5px;
            color: #374151;
            font-size: 14px;
        }
        
        .control-group select,
        .control-group input {
            width: 100%;
            padding: 10px;
            border: 2px solid #e5e7eb;
            border-radius: 6px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        
        .control-group select:focus,
        .control-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        /* Buttons */
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 14px;
        }
        
        .btn-primary {
            background: #667eea;
            color: white;
        }
        
        .btn-primary:hover {
            background: #5568d3;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        
        .btn-secondary {
            background: #6b7280;
            color: white;
        }
        
        .btn-secondary:hover {
            background: #4b5563;
        }
        
        .btn-success {
            background: #10b981;
            color: white;
        }
        
        .btn-success:hover {
            background: #059669;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
        }
        
        .btn-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        /* Stats */
        .stats-box {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
        }
        
        .stats-box h3 {
            margin: 0 0 10px 0;
            font-size: 18px;
        }
        
        .stats-box p {
            margin: 5px 0;
            font-size: 14px;
        }
        
        .stats-number {
            font-size: 36px;
            font-weight: 700;
            margin: 10px 0;
        }
        
        /* Utility */
        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            padding: 10px;
            background: #f9fafb;
            border-radius: 6px;
        }
        
        .checkbox-label input {
            width: 18px;
            height: 18px;
        }
        
        .arrow {
            transition: transform 0.3s;
            font-size: 12px;
        }
        
        .expanded .arrow {
            transform: rotate(90deg);
        }
        
        .section-divider {
            height: 2px;
            background: linear-gradient(90deg, transparent, #667eea, transparent);
            margin: 30px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏛️ Tender Retrieve Manager</h1>
            <p class="subtitle">Select categories and fetch business opportunities</p>
        </div>
        
        <form method="post" action="/fetch">
            <!-- Saved Selections Card (Moved to Top) -->
            <div class="card" style="margin-bottom: 30px; border: 2px solid #667eea;">
                <div class="card-header" style="background: #eef2ff; color: #4338ca;">
                    💾 Saved Lists
                </div>
                <div class="card-body">
                    <div style="display: flex; align-items: center; gap: 15px; flex-wrap: wrap;">
                        <div style="flex: 1; min-width: 250px;">
                            <select id="savedSelections" class="form-control" style="width: 100%; padding: 12px; border-radius: 6px; border: 1px solid #ced4da; font-size: 16px;">
                                <option value="">-- Select a saved list --</option>
                            </select>
                        </div>
                        <div style="display: flex; gap: 10px; align-items: center;">
                            <button type="button" class="btn btn-success" onclick="loadSelection()" style="padding: 12px 20px;">
                                📂 Load List
                            </button>
                            <button type="button" class="btn btn-primary" onclick="saveSelection()" style="padding: 12px 20px;">
                                💾 Save Current Settings
                            </button>
                            <button type="button" class="btn btn-danger" onclick="deleteSelection()" style="padding: 12px 20px;">
                                🗑️ Delete
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Date Filter Card -->
            <div class="card">
                <div class="card-header">
                    📅 Date Filter
                </div>
                <div class="card-body">
                    <div class="controls">
                        <div class="control-group">
                            <label>Quick Select</label>
                            <select name="date_mode" id="dateModeSelect" onchange="updateDateRange(this)">
                                <option value="last_working_day" selected>Last Working Day (Default)</option>
                                <option value="today">Last 24 Hours (Today)</option>
                                <option value="last_7_days">Last 7 Days</option>
                                <option value="last_14_days">Last 14 Days</option>
                                <option value="last_31_days">Last 31 Days</option>
                                <option value="last_90_days">Last 90 Days</option>
                                <option value="last_365_days">Last 365 Days</option>
                                <option value="specific_date">Specific Date</option>
                                <option value="custom">Custom Range</option>
                            </select>
                        </div>
                        <div class="control-group" id="startDateGroup">
                            <label>Start Date</label>
                            <input type="date" name="date_start">
                        </div>
                        <div class="control-group" id="endDateGroup">
                            <label>End Date</label>
                            <input type="date" name="date_end">
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="section-divider"></div>
            
            <!-- Other Procurement Sources (Consolidated) -->
            <div class="card">
                <div class="card-header">
                    <span>🌍 Other Procurement Sources</span>
                </div>
                <div class="card-body">
                    
                    <!-- SAP Ariba -->
                    <div class="subcategory-item">
                        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                            <div>
                                <input type="checkbox" name="use_ariba" value="1" id="chk_ariba">
                                <label for="chk_ariba" style="font-weight: 600;">SAP Ariba - Singapore</label>
                            </div>
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <label style="font-size: 13px; color: #4b5563;">Pages:</label>
                                <select name="ariba_pages" class="form-control" style="padding: 4px; border-radius: 4px; border: 1px solid #ced4da; font-size: 13px;">
                                    <option value="1">1 (Max 10 items)</option>
                                    <option value="2">2 (Max 20 items)</option>
                                    <option value="3" selected>3 (Max 30 items) - Default</option>
                                    <option value="5">5 (Max 50 items)</option>
                                    <option value="10">10 (Max 100 items)</option>
                                    <option value="custom">Custom</option>
                                </select>
                                <input type="number" name="ariba_pages_custom" placeholder="#" 
                                       style="display: none; width: 60px; padding: 4px; border-radius: 4px; border: 1px solid #ced4da;" min="1" max="100">
                            </div>
                        </div>
                    </div>
                    <script>
                        document.querySelector('select[name="ariba_pages"]').addEventListener('change', function(e) {
                             const customInput = document.querySelector('input[name="ariba_pages_custom"]');
                             if (e.target.value === 'custom') {
                                 customInput.style.display = 'block';
                                 customInput.required = true;
                             } else {
                                 customInput.style.display = 'none';
                                 customInput.required = false;
                             }
                        });
                    </script>

                    <!-- Sesami -->
                    <div class="subcategory-item" style="margin-top: 10px;">
                        <input type="checkbox" name="use_sesami" value="1" id="chk_sesami">
                        <label for="chk_sesami" style="font-weight: 600;">Sesami Business Opportunities</label>
                    </div>

                    <!-- TenderBoard -->
                    <div class="subcategory-item" style="margin-top: 10px;">
                        <input type="checkbox" name="feed_url" value="ENABLE_TENDERBOARD" id="chk_tb">
                        <label for="chk_tb" style="font-weight: 600;">TenderBoard (SUSS, SIM, SMU, etc.)</label>
                    </div>

                    <!-- JPMC -->
                    <div class="subcategory-item" style="margin-top: 10px;">
                        <input type="checkbox" name="feed_url" value="ENABLE_JPMC" id="chk_jpmc">
                        <label for="chk_jpmc" style="font-weight: 600;">JPMC Brunei Tenders</label>
                    </div>

                    <!-- ST Logistics -->
                    <div class="subcategory-item" style="margin-top: 10px;">
                        <input type="checkbox" name="feed_url" value="ENABLE_STLOGS" id="chk_stlogs">
                        <label for="chk_stlogs" style="font-weight: 600;">ST Logistics (Find Opportunities)</label>
                    </div>
                </div>
            </div>
            
            <div class="section-divider"></div>
            
            <!-- Feed Selection Card (GeBIZ) -->
            <div class="card">
                <div class="card-header">
                    <span>📋 GeBIZ Feed Selection</span>
                    <div class="btn-group">
                        <button type="button" class="btn btn-secondary" onclick="expandAll()">Expand All</button>
                        <button type="button" class="btn btn-secondary" onclick="collapseAll()">Collapse All</button>
                        <button type="button" class="btn btn-secondary" onclick="selectAll()">Select All</button>
                        <button type="button" class="btn btn-secondary" onclick="clearAll()">Clear All</button>
                    </div>
                </div>
                
                
                <div class="card-body">
                    <!-- Feed Type Tabs -->
                    <div class="feed-type-tabs">
                        <div class="feed-type-tab active" onclick="switchFeedType('opportunities')">
                            💼 Business Opportunities
                        </div>
                        <div class="feed-type-tab" onclick="switchFeedType('awards')">
                            🏆 Awards
                        </div>
                        <div class="feed-type-tab" onclick="switchFeedType('both')">
                            📊 Both
                        </div>
                    </div>
                    
                    <!-- Opportunities Content -->
                    <div id="opportunities-content" class="feed-type-content active">
                        <div class="category-grid">
                        {% for main, subs in feeds.items() %}
                            <div class="category-card">
                                <div class="category-header" onclick="toggleCategory(this)">
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <input type="checkbox" onclick="toggleHeaderGroup(this, event)" title="Select all in group">
                                        <span>{{ main }}</span>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <span class="category-count">{{ subs|length }}</span>
                                        <span class="arrow">▶</span>
                                    </div>
                                </div>
                                <div class="category-body">
                                    {% for sub, types in subs.items() %}
                                        {% if types.get('bo') %}
                                        <div class="subcategory-item">
                                            <input type="checkbox" name="feed_url" value="{{ types['bo'] }}" 
                                                   id="bo_{{ loop.index0 }}_{{ loop.index }}" 
                                                   data-type="opportunities">
                                            <label for="bo_{{ loop.index0 }}_{{ loop.index }}">{{ sub }}</label>
                                        </div>
                                        {% endif %}
                                    {% endfor %}
                                </div>
                            </div>
                        {% endfor %}
                        </div>
                    </div>
                    
                    <!-- Awards Content -->
                    <div id="awards-content" class="feed-type-content">
                        <div class="category-grid">
                        {% for main, subs in feeds.items() %}
                            <div class="category-card">
                                <div class="category-header" onclick="toggleCategory(this)">
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <input type="checkbox" onclick="toggleHeaderGroup(this, event)" title="Select all in group">
                                        <span>GeBIZ - {{ main }}</span>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <span class="category-count">{{ subs|length }}</span>
                                        <span class="arrow">▶</span>
                                    </div>
                                </div>
                                <div class="category-body">
                                    {% for sub, types in subs.items() %}
                                        {% if types.get('awd') %}
                                        <div class="subcategory-item">
                                            <input type="checkbox" name="feed_url" value="{{ types['awd'] }}" 
                                                   id="awd_{{ loop.index0 }}_{{ loop.index }}" 
                                                   data-type="awards">
                                            <label for="awd_{{ loop.index0 }}_{{ loop.index }}">{{ sub }}</label>
                                        </div>
                                        {% endif %}
                                    {% endfor %}
                                </div>
                            </div>
                        {% endfor %}
                        </div>
                    </div>
                    
                    <!-- Both Content -->
                    <div id="both-content" class="feed-type-content">
                        <div class="category-grid">
                        {% for main, subs in feeds.items() %}
                            <div class="category-card">
                                <div class="category-header" onclick="toggleCategory(this)">
                                    <span>GeBIZ - {{ main }}</span>
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <span class="category-count">{{ subs|length }}</span>
                                        <span class="arrow">▶</span>
                                    </div>
                                </div>
                                <div class="category-body">
                                    {% for sub, types in subs.items() %}
                                        {% if types.get('bo') %}
                                        <div class="subcategory-item">
                                            <input type="checkbox" name="feed_url" value="{{ types['bo'] }}" 
                                                   id="both_bo_{{ loop.index0 }}_{{ loop.index }}" 
                                                   data-type="both">
                                            <label for="both_bo_{{ loop.index0 }}_{{ loop.index }}">{{ sub }} (Opportunity)</label>
                                        </div>
                                        {% endif %}
                                        {% if types.get('awd') %}
                                        <div class="subcategory-item">
                                            <input type="checkbox" name="feed_url" value="{{ types['awd'] }}" 
                                                   id="both_awd_{{ loop.index0 }}_{{ loop.index }}" 
                                                   data-type="both">
                                            <label for="both_awd_{{ loop.index0 }}_{{ loop.index }}">{{ sub }} (Award)</label>
                                        </div>
                                        {% endif %}
                                    {% endfor %}
                                </div>
                            </div>
                        {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="section-divider"></div>
            
            <!-- Actions -->
            <div class="card">
                <div class="card-body">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px;">
                        <label class="checkbox-label" style="display:none">
                            <input type="checkbox" name="use_html" value="1">
                            <span>Include HTML Fallback (Today's Opportunities Only)</span>
                        </label>

                         <button type="submit" class="btn btn-primary">🚀 Fetch Selected Feeds</button>
                    </div>
                    
                    <!-- Results (Merged) -->
                    {% if count is not none %}
                    <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee;">
                        <div class="stats-box" style="margin-bottom: 0;">
                            <h3>✅ Fetch Complete</h3>
                            <div class="stats-number">{{ count }}</div>
                            <p>items captured at {{ ts }}</p>
                            <p>Filter mode: <strong>{{ date_mode }}</strong></p>
                            <div style="margin-top: 15px;">
                                <button type="button" class="btn btn-success" onclick="submitExport()">📥 Export to Excel</button>
                            </div>
                        </div>
                    </div>
                    {% endif %}
                    
                    {% if download_ready %}
                    <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee;">
                        <div class="stats-box" style="margin-bottom: 0;">
                            <h3>🎉 Export Successful!</h3>
                            <p><a href="/download" style="color: white; text-decoration: underline; font-weight: 600;">Download {{ export_filename }}</a></p>
                        </div>
                    </div>
                    {% endif %}
                </div>
            </div>
        </form>
    </div>
    
    <script>
        function submitExport() {
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/export';
            document.body.appendChild(form);
            form.submit();
        }

        // Feed Type Switching
        function switchFeedType(type) {
            // Update tabs
            document.querySelectorAll('.feed-type-tab').forEach(tab => {
                tab.classList.remove('active');
            });
            event.target.classList.add('active');
            
            // Update content
            document.querySelectorAll('.feed-type-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(type + '-content').classList.add('active');
        }
        
        // Category Toggle
        function toggleCategory(header) {
            const body = header.nextElementSibling;
            const arrow = header.querySelector('.arrow');
            body.classList.toggle('expanded');
            header.classList.toggle('expanded');
        }

        // Header Checkbox Logic
        function toggleHeaderGroup(checkbox, event) {
            event.stopPropagation(); // Prevent accordion toggle
            const header = checkbox.closest('.category-header');
            const card = header.parentElement;
            const body = card.querySelector('.category-body');
            const checkboxes = body.querySelectorAll('input[type="checkbox"]');
            
            checkboxes.forEach(cb => {
                cb.checked = checkbox.checked;
            });
        }
        
        // Expand/Collapse All
        function expandAll() {
            document.querySelectorAll('.category-body').forEach(body => {
                body.classList.add('expanded');
            });
            document.querySelectorAll('.category-header').forEach(header => {
                header.classList.add('expanded');
            });
        }
        
        function collapseAll() {
            document.querySelectorAll('.category-body').forEach(body => {
                body.classList.remove('expanded');
            });
            document.querySelectorAll('.category-header').forEach(header => {
                header.classList.remove('expanded');
            });
        }
        
        // Select/Clear All
        function selectAll() {
            const activeContent = document.querySelector('.feed-type-content.active');
            activeContent.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                cb.checked = true;
            });
        }
        
        function clearAll() {
            const activeContent = document.querySelector('.feed-type-content.active');
            activeContent.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                cb.checked = false;
            });
        }
        
        // Selection Management
        function getCurrentFeedType() {
            const activeTab = document.querySelector('.feed-type-tab.active');
            const text = activeTab.textContent.trim();
            if (text.includes('Business Opportunities')) return 'bo';
            if (text.includes('Awards')) return 'awd';
            return 'both';
        }
        
        function getSelectedFeeds() {
            const activeContent = document.querySelector('.feed-type-content.active');
            const checkboxes = activeContent.querySelectorAll('input[type="checkbox"]:checked');
            return Array.from(checkboxes).map(cb => cb.value);
        }
        
        function loadSelectionsList() {
            fetch('/selections/list')
                .then(r => r.json())
                .then(selections => {
                    const select = document.getElementById('savedSelections');
                    select.innerHTML = '<option value="">-- Select a saved list --</option>';
                    selections.forEach(sel => {
                        const option = document.createElement('option');
                        option.value = sel.name;
                        const typeIcon = sel.feed_type === 'bo' ? '💼' : sel.feed_type === 'awd' ? '🏆' : '📊';
                        option.textContent = `${typeIcon} ${sel.name} (${sel.count} feeds)`;
                        select.appendChild(option);
                    });
                })
                .catch(err => console.error('Error loading selections:', err));
        }
        
        function saveSelection() {
            const name = prompt('Enter a name for this selection:');
            if (!name) return;
            
            const feedType = getCurrentFeedType();
            
            // Collect ALL checked boxes including non-GeBIZ
            const selectedFeeds = [];
            
            // 1. GeBIZ Feeds & Other Checkboxes (TenderBoard, JPMC)
            document.querySelectorAll('input[type="checkbox"][name="feed_url"]:checked').forEach(cb => {
                selectedFeeds.push(cb.value);
            });

            // 2. Auxiliary Settings (Ariba, Sesami, HTML)
            if (document.querySelector('input[name="use_ariba"]').checked) selectedFeeds.push('SPECIAL:ARIBA');
            if (document.querySelector('input[name="use_sesami"]').checked) selectedFeeds.push('SPECIAL:SESAMI');
            if (document.querySelector('input[name="use_html"]').checked) selectedFeeds.push('SPECIAL:HTML');
            
            if (selectedFeeds.length === 0) {
                alert('No feeds or options selected!');
                return;
            }
            
            fetch('/selections/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: name,
                    feed_type: feedType, // Keeps track of tab preference
                    selected_feeds: selectedFeeds
                })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    alert(data.message);
                    loadSelectionsList();
                } else {
                    alert('Error: ' + data.message);
                }
            })
            .catch(err => {
                console.error('Error saving selection:', err);
                alert('Error saving selection');
            });
        }
        
        function loadSelection() {
            const select = document.getElementById('savedSelections');
            const name = select.value;
            
            if (!name) {
                alert('Please select a saved list first');
                return;
            }
            
            fetch(`/selections/load/${encodeURIComponent(name)}`)
                .then(r => r.json())
                .then(data => {
                    if (!data.success) {
                        alert('Error: ' + data.message);
                        return;
                    }
                    
                    const selection = data.selection;
                    
                    // Switch to correct feed type tab
                    let tabToClick = 'opportunities';
                    if (selection.feed_type === 'awd') tabToClick = 'awards';
                    if (selection.feed_type === 'both') tabToClick = 'both';
                    
                    document.querySelectorAll('.feed-type-tab').forEach(tab => {
                        tab.classList.remove('active');
                        if (tab.textContent.includes('Business Opportunities') && tabToClick === 'opportunities') {
                            tab.classList.add('active');
                        } else if (tab.textContent.includes('Awards') && tabToClick === 'awards') {
                            tab.classList.add('active');
                        } else if (tab.textContent.includes('Both') && tabToClick === 'both') {
                            tab.classList.add('active');
                        }
                    });
                    
                    document.querySelectorAll('.feed-type-content').forEach(content => {
                        content.classList.remove('active');
                    });
                    document.getElementById(tabToClick + '-content').classList.add('active');
                    
                    // Clear ALL checkboxes first
                    document.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
                    
                    // Check the selected feeds & options
                    selection.selected_feeds.forEach(item => {
                        if (item === 'SPECIAL:ARIBA') {
                            document.querySelector('input[name="use_ariba"]').checked = true;
                        } else if (item === 'SPECIAL:SESAMI') {
                            document.querySelector('input[name="use_sesami"]').checked = true;
                        } else if (item === 'SPECIAL:HTML') {
                            document.querySelector('input[name="use_html"]').checked = true;
                        } else {
                            // Feed URL or Scraper Token
                            const checkbox = document.querySelector(`input[type="checkbox"][value="${item}"]`);
                            if (checkbox) checkbox.checked = true;
                        }
                    });
                    
                    alert(`Loaded "${selection.name}" (${selection.selected_feeds.length} items)`);
                })
                .catch(err => {
                    console.error('Error loading selection:', err);
                    alert('Error loading selection');
                });
        }
        
        function deleteSelection() {
            const select = document.getElementById('savedSelections');
            const name = select.value;
            
            if (!name) {
                alert('Please select a saved list first');
                return;
            }
            
            if (!confirm(`Delete selection "${name}"?`)) {
                return;
            }
            
            fetch(`/selections/delete/${encodeURIComponent(name)}`, {
                method: 'DELETE'
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    alert(data.message);
                    loadSelectionsList();
                } else {
                    alert('Error: ' + data.message);
                }
            })
            .catch(err => {
                console.error('Error deleting selection:', err);
                alert('Error deleting selection');
            });
        }
        
        // Load selections list on page load
        document.addEventListener('DOMContentLoaded', function() {
            loadSelectionsList();
            // Ensure logic runs for the default selection (Last Working Day)
            updateDateRange(document.getElementById('dateModeSelect'));
        });

        // Date Range Logic
        function updateDateRange(select) {
            const form = select.form;
            const mode = select.value;
            const startDateInput = form.date_start;
            const endDateInput = form.date_end;
            
            const startGroup = document.getElementById('startDateGroup');
            const endGroup = document.getElementById('endDateGroup');
            const startLabel = startGroup.querySelector('label');
            
            // Reset UI states
            endGroup.style.display = 'block';
            startLabel.textContent = 'Start Date';
            
            // Helper to format date as YYYY-MM-DD
            const formatDate = (date) => {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                return `${year}-${month}-${day}`;
            };
            
            const today = new Date();
            let start = null;
            let end = today; // End is usually today
            
            if (mode === 'today') {
                // User requested "start 1 day earlier" for Last 24 Hours
                start = new Date(today);
                start.setDate(today.getDate() - 1);
            } else if (mode === 'last_working_day') {
                start = new Date(today);
                const day = start.getDay(); // 0 is Sunday, 1 is Monday
                if (day === 1) { // Monday -> Friday (3 days ago)
                     start.setDate(today.getDate() - 3);
                } else if (day === 0) { // Sunday -> Friday (2 days ago)
                     start.setDate(today.getDate() - 2);
                } else {
                     start.setDate(today.getDate() - 1);
                }
                // Typically LWD is a single day fetch for consistency
                // But user requests End Date to be TODAY for range coverage.
                end = today;
            } else if (mode === 'last_7_days') {
                start = new Date(today); start.setDate(today.getDate() - 7);
            } else if (mode === 'last_14_days') {
                start = new Date(today); start.setDate(today.getDate() - 14);
            } else if (mode === 'last_31_days') {
                start = new Date(today); start.setDate(today.getDate() - 31);
            } else if (mode === 'last_90_days') {
                start = new Date(today); start.setDate(today.getDate() - 90);
            } else if (mode === 'last_365_days') {
                start = new Date(today); start.setDate(today.getDate() - 365);
            } else if (mode === 'specific_date') {
                startLabel.textContent = 'Date';
                endGroup.style.display = 'none';
            }
            
            if (start) {
                startDateInput.value = formatDate(start);
                if (end) endDateInput.value = formatDate(end);
            }
            
            // Clear inputs if custom
            if (mode === 'custom') {
                startDateInput.value = '';
                endDateInput.value = '';
            }
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'Starting app on port {port}')
    app.run(host='0.0.0.0', port=port, debug=True)
