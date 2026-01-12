import pandas as pd
import yaml
from pathlib import Path

def generate_config_from_excel():
    try:
        df = pd.read_excel('GeBIZ_RSS_Feeds_2.xlsx')
        
        # Clean column names (strip whitespace)
        df.columns = [c.strip() for c in df.columns]
        
        # Forward fill Main Header to handle potential merged cells visual representation
        if 'Main Header' in df.columns:
            df['Main Header'] = df['Main Header'].ffill()
            
        config = {'feeds': {}}
        
        for _, row in df.iterrows():
            main = str(row.get('Main Header', 'Uncategorized')).strip()
            sub = str(row.get('Sub Header', 'General')).strip()
            bo_link = row.get('Opportunities Link')
            awd_link = row.get('Award Link')
            
            # Clean up links
            if pd.isna(bo_link): bo_link = None
            else: bo_link = str(bo_link).strip()
            
            if pd.isna(awd_link): awd_link = None
            else: awd_link = str(awd_link).strip()
            
            if not bo_link and not awd_link:
                continue
                
            if main not in config['feeds']:
                config['feeds'][main] = {}
                
            if sub not in config['feeds'][main]:
                config['feeds'][main][sub] = {}
                
            if bo_link:
                config['feeds'][main][sub]['bo'] = bo_link
            if awd_link:
                config['feeds'][main][sub]['awd'] = awd_link
                
        out_path = Path('config/feeds.yaml')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(out_path, 'w') as f:
            yaml.dump(config, f, sort_keys=False)
            
        print(f"Generated config/feeds.yaml from Excel")
        print(f"Main Categories: {len(config['feeds'])}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    generate_config_from_excel()
