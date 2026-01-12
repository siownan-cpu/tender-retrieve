from docx import Document
import yaml
from pathlib import Path

def generate_hierarchical_config():
    try:
        doc = Document('Gebiz RSS Feeds.docx')
        items = []
        for p in doc.paragraphs:
            t = p.text.strip()
            if t: items.append(t)
        
        config = {'feeds': {}}
        current_main = "Uncategorized"
        
        i = 0
        while i < len(items):
            txt = items[i]
            
            # Skip if we hit a link block keyword accidentally (should be handled by inner loop, but safety check)
            if txt in ('Business Opportunity', 'Award') or 'http' in txt:
                 i += 1
                 continue
                 
            # Check next item to decide if Main or Sub
            if i + 1 >= len(items):
                break
                
            next_txt = items[i+1]
            
            # Heuristic: If next line is start of a link block (BO/AWD/URL), then 'txt' is a SUB category.
            # Otherwise, 'txt' is a MAIN category.
            is_sub = False
            if next_txt in ('Business Opportunity', 'Award') or 'http' in next_txt:
                is_sub = True
            
            if is_sub:
                sub_cat = txt
                bo_url = None
                awd_url = None
                
                # Absorb links
                j = i + 1
                while j < len(items):
                    val = items[j]
                    # Check if val is start of NEXT header
                    # A header is anything NOT BO, Award, or URL.
                    if val not in ('Business Opportunity', 'Award') and 'http' not in val:
                        break
                        
                    if val == 'Business Opportunity':
                        if j+1 < len(items) and 'http' in items[j+1]:
                            bo_url = items[j+1].strip()
                    elif val == 'Award':
                        if j+1 < len(items) and 'http' in items[j+1]:
                            awd_url = items[j+1].strip()
                    j += 1
                
                # Add to config
                if current_main not in config['feeds']:
                    config['feeds'][current_main] = {}
                
                # If bo_url or awd_url found, add it
                if bo_url or awd_url:
                    config['feeds'][current_main][sub_cat] = {}
                    if bo_url: config['feeds'][current_main][sub_cat]['bo'] = bo_url
                    if awd_url: config['feeds'][current_main][sub_cat]['awd'] = awd_url
                
                # Move index
                i = j
                
            else:
                # It's a Main Category
                current_main = txt
                i += 1
        
        out_path = Path('config/feeds.yaml')
        out_path.parent.mkdir(parents=True, exist_ok=True) # Ensure 'config' directory exists
        with open(out_path, 'w') as f:
            yaml.dump(config, f, sort_keys=False)
            
        print(f"Generated hierarchical config/feeds.yaml")
        print(f"Main Categories found: {list(config['feeds'].keys())}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    generate_hierarchical_config()
