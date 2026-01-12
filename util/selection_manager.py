"""
Selection List Manager

Allows users to save and load feed selection presets
"""

import json
from pathlib import Path
from datetime import datetime

# Directory for storing selection lists
SELECTIONS_DIR = Path('config/selections')

def ensure_selections_dir():
    """Create selections directory if it doesn't exist"""
    SELECTIONS_DIR.mkdir(parents=True, exist_ok=True)

def save_selection(name, feed_type, selected_feeds):
    """
    Save a selection list
    
    Args:
        name: Name for this selection
        feed_type: 'bo', 'awd', or 'both'
        selected_feeds: List of feed URLs
        
    Returns:
        bool: Success status
    """
    ensure_selections_dir()
    
    # Sanitize name for filename
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_name:
        return False, "Invalid selection name"
    
    filename = f"{safe_name}.json"
    filepath = SELECTIONS_DIR / filename
    
    selection_data = {
        'name': name,
        'feed_type': feed_type,
        'selected_feeds': selected_feeds,
        'created': datetime.now().isoformat(),
        'count': len(selected_feeds)
    }
    
    try:
        with open(filepath, 'w') as f:
            json.dump(selection_data, f, indent=2)
        return True, f"Selection '{name}' saved successfully"
    except Exception as e:
        return False, f"Error saving selection: {str(e)}"

def load_selection(name):
    """
    Load a selection list
    
    Args:
        name: Name of the selection to load
        
    Returns:
        dict or None: Selection data
    """
    ensure_selections_dir()
    
    # Sanitize name for filename
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    filename = f"{safe_name}.json"
    filepath = SELECTIONS_DIR / filename
    
    if not filepath.exists():
        return None
    
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading selection: {e}")
        return None

def list_selections():
    """
    List all saved selections
    
    Returns:
        list: List of selection metadata
    """
    ensure_selections_dir()
    
    selections = []
    for filepath in SELECTIONS_DIR.glob('*.json'):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                selections.append({
                    'name': data.get('name', filepath.stem),
                    'feed_type': data.get('feed_type', 'unknown'),
                    'count': data.get('count', 0),
                    'created': data.get('created', 'unknown')
                })
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            continue
    
    # Sort by name
    selections.sort(key=lambda x: x['name'])
    return selections

def delete_selection(name):
    """
    Delete a selection list
    
    Args:
        name: Name of the selection to delete
        
    Returns:
        bool: Success status
    """
    ensure_selections_dir()
    
    # Sanitize name for filename
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    filename = f"{safe_name}.json"
    filepath = SELECTIONS_DIR / filename
    
    if not filepath.exists():
        return False, "Selection not found"
    
    try:
        filepath.unlink()
        return True, f"Selection '{name}' deleted successfully"
    except Exception as e:
        return False, f"Error deleting selection: {str(e)}"
