"""
HTML Fallback for GeBIZ Opportunities

⚠️ WARNING: HTML scraping is UNRELIABLE and NOT RECOMMENDED
   - Use RSS feeds instead (they are the official API)
   - HTML structure can change at any time
   - May violate GeBIZ Terms of Service
   - Results are often inaccurate/incomplete
   
This fallback is provided as last resort only. It is DISABLED by default.
"""

import requests
from bs4 import BeautifulSoup

# GeBIZ Today's Opportunities page
TODAY_URL = 'https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml?origin=opportunities'

# Set to False to disable HTML fallback (RECOMMENDED)
HTML_FALLBACK_ENABLED = False

def fetch_today_opportunities():
    """
    Attempt to scrape today's opportunities from GeBIZ website
    
    ⚠️ WARNING: This is highly unreliable and may return garbage data!
    
    Returns:
        list: List of items (usually empty or inaccurate)
    """
    
    if not HTML_FALLBACK_ENABLED:
        print("\n⚠️  HTML FALLBACK IS DISABLED")
        print("   Reason: Unreliable and not recommended")
        print("   Recommendation: Use RSS feeds only")
        print("   To enable: Set HTML_FALLBACK_ENABLED = True in collector/html_fallback.py\n")
        return []
    
    print("\n" + "="*80)
    print("⚠️  HTML FALLBACK ACTIVATED (NOT RECOMMENDED)")
    print("="*80)
    print("WARNING: HTML scraping is unreliable and may violate terms of service")
    print("Attempting to fetch: " + TODAY_URL)
    print("="*80 + "\n")
    
    items = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        resp = requests.get(TODAY_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        
        print(f"HTTP Status: {resp.status_code}")
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Try multiple selectors to find opportunity listings
        # Note: These may break if GeBIZ changes their HTML structure
        
        # Attempt 1: Look for specific opportunity containers
        opportunities = soup.select('div.opportunity-item, div.tender-item, div.listing-item')
        
        if not opportunities:
            # Attempt 2: Look for table rows
            opportunities = soup.select('table.opportunities tbody tr, table.tenders tbody tr')
        
        if not opportunities:
            # Attempt 3: Generic cards (VERY unreliable)
            opportunities = soup.select('div.card')
            print("WARNING: Using generic card selector - results will be very unreliable!")
        
        print(f"Found {len(opportunities)} potential opportunity elements")
        
        for idx, opp in enumerate(opportunities, 1):
            # Extract text
            text = opp.get_text(' ', strip=True)
            
            # Skip if too short (likely not an opportunity)
            if len(text) < 20:
                continue
            
            # Try to find link
            link = None
            a_tag = opp.find('a', href=True)
            if a_tag:
                link = a_tag['href']
                # Make absolute URL if relative
                if link and not link.startswith('http'):
                    link = 'https://www.gebiz.gov.sg' + link
            
            # Try to extract title (first h3, h4, strong, or first 100 chars)
            title = ''
            title_tag = opp.find(['h3', 'h4', 'h5', 'strong'])
            if title_tag:
                title = title_tag.get_text(strip=True)
            else:
                title = text[:100]
            
            item = {
                'source': 'html_fallback',
                'title': title,
                'link': link,
                'summary': text[:500],  # Limit summary length
                'published': '',  # Cannot reliably extract from HTML
                'feed_url': 'HTML_FALLBACK'
            }
            
            items.append(item)
            
            if idx <= 3:  # Show first 3 for debugging
                print(f"\n  Item {idx}:")
                print(f"    Title: {title[:60]}...")
                print(f"    Link: {link or 'No link'}")
        
        print(f"\n✓ Extracted {len(items)} items from HTML")
        print("⚠️  IMPORTANT: These results may be inaccurate!")
        print("   Recommendation: Verify results manually")
        print("="*80 + "\n")
        
    except requests.exceptions.RequestException as e:
        print(f"✗ HTTP Error: {e}")
        print("HTML fallback failed - network/access issue")
        print("="*80 + "\n")
    except Exception as e:
        print(f"✗ Parsing Error: {e}")
        print("HTML fallback failed - could not parse page")
        print("="*80 + "\n")
    
    return items


def enable_html_fallback():
    """
    Enable HTML fallback (not recommended)
    
    Call this function to enable HTML scraping at runtime.
    """
    global HTML_FALLBACK_ENABLED
    HTML_FALLBACK_ENABLED = True
    print("⚠️  HTML fallback ENABLED - use with caution!")


def disable_html_fallback():
    """
    Disable HTML fallback (recommended)
    """
    global HTML_FALLBACK_ENABLED
    HTML_FALLBACK_ENABLED = False
    print("✓ HTML fallback DISABLED (recommended)")
