
from collector.rss_client import load_feeds_config

def categorize_selected_urls(selected_urls):
    """
    Parses a list of selected RSS URLs and returns a dictionary
    grouping them by type ('BO' or 'AWD') and their Category Name.
    
    Structure:
    {
        'BO': ['Advertising Services', 'Software & Licences'],
        'AWD': ['Construction Works']
    }
    """
    feeds = load_feeds_config()
    
    mapping = {'BO': set(), 'AWD': set()}
    
    for main_cat_key, sub_cats in feeds.items():
        # Clean Main Category (e.g. "9. Dental..." -> "Dental...")
        clean_main = main_cat_key.split('. ', 1)[1] if '. ' in main_cat_key else main_cat_key
        
        if isinstance(sub_cats, dict):
            for sub_cat_key, urls in sub_cats.items():
                # Clean Sub Category (e.g. "a. Others" -> "Others")
                clean_sub = sub_cat_key.split('. ', 1)[1] if '. ' in sub_cat_key else sub_cat_key
                
                # Format: "Main > Sub"
                full_name = f"{clean_main} > {clean_sub}"
                
                # Check BO Logic
                if 'bo' in urls:
                    cfg_url = urls['bo']
                    for s_url in selected_urls:
                        # Match Logic:
                        # 1. Exact Match
                        # 2. Selected is substring of Config (e.g. filename only provided)
                        # 3. Config is substring of Selected (unlikely but safe)
                        if s_url and (s_url == cfg_url or s_url in cfg_url or cfg_url in s_url):
                             mapping['BO'].add(full_name)

                # Check AWD Logic
                if 'awd' in urls:
                    cfg_url = urls['awd']
                    for s_url in selected_urls:
                        if s_url and (s_url == cfg_url or s_url in cfg_url or cfg_url in s_url):
                             mapping['AWD'].add(full_name)
    
    return {
        'BO': list(mapping['BO']),
        'AWD': list(mapping['AWD'])
    }
