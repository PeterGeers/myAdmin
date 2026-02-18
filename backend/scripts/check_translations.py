#!/usr/bin/env python3

"""
Backend Translation Completeness Checker

Checks that all translation keys exist in both Dutch (nl) and English (en) languages.
Reports missing keys, extra keys, and provides statistics.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Colors for console output
class Colors:
    RESET = '\033[0m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    CYAN = '\033[36m'

# Translation file paths
BACKEND_DIR = Path(__file__).parent.parent
TRANSLATIONS_DIR = BACKEND_DIR / 'translations'
LANGUAGES = ['nl', 'en']

def load_json(file_path: Path) -> Dict:
    """Load JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"{Colors.RED}Error loading {file_path}: {e}{Colors.RESET}")
        return None

def get_all_keys(obj: Dict, prefix: str = '') -> List[str]:
    """Get all keys from nested dictionary"""
    keys = []
    
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        
        if isinstance(value, dict):
            keys.extend(get_all_keys(value, full_key))
        else:
            keys.append(full_key)
    
    return keys

def compare_keys(keys1: List[str], keys2: List[str]) -> Tuple[List[str], List[str]]:
    """Compare two sets of keys"""
    set1 = set(keys1)
    set2 = set(keys2)
    
    missing = [k for k in keys1 if k not in set2]
    extra = [k for k in keys2 if k not in set1]
    
    return missing, extra

def check_translations() -> bool:
    """Check all backend translations"""
    print(f"{Colors.BLUE}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║      Backend Translation Completeness Checker            ║")
    print("║         Checking Dutch (nl) vs English (en)               ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}\n")
    
    # Check if translations directory exists
    if not TRANSLATIONS_DIR.exists():
        print(f"{Colors.YELLOW}No translations directory found at {TRANSLATIONS_DIR}{Colors.RESET}")
        print(f"{Colors.YELLOW}Backend translations are optional (using Flask-Babel){Colors.RESET}")
        return True
    
    # Find all translation files
    nl_files = list((TRANSLATIONS_DIR / 'nl').glob('*.json')) if (TRANSLATIONS_DIR / 'nl').exists() else []
    en_files = list((TRANSLATIONS_DIR / 'en').glob('*.json')) if (TRANSLATIONS_DIR / 'en').exists() else []
    
    if not nl_files and not en_files:
        print(f"{Colors.YELLOW}No translation files found{Colors.RESET}")
        print(f"{Colors.YELLOW}Backend uses Flask-Babel for translations{Colors.RESET}")
        return True
    
    # Get all unique file names
    all_files = set([f.name for f in nl_files] + [f.name for f in en_files])
    
    has_errors = False
    all_stats = []
    
    for filename in sorted(all_files):
        print(f"\n{Colors.CYAN}Checking file: {filename}{Colors.RESET}")
        print("=" * 60)
        
        nl_path = TRANSLATIONS_DIR / 'nl' / filename
        en_path = TRANSLATIONS_DIR / 'en' / filename
        
        # Check if both files exist
        if not nl_path.exists():
            print(f"{Colors.RED}✗ Missing Dutch file: {nl_path}{Colors.RESET}")
            has_errors = True
            continue
        
        if not en_path.exists():
            print(f"{Colors.RED}✗ Missing English file: {en_path}{Colors.RESET}")
            has_errors = True
            continue
        
        # Load translations
        nl_data = load_json(nl_path)
        en_data = load_json(en_path)
        
        if nl_data is None or en_data is None:
            has_errors = True
            continue
        
        # Get all keys
        nl_keys = get_all_keys(nl_data)
        en_keys = get_all_keys(en_data)
        
        # Compare keys
        missing, extra = compare_keys(nl_keys, en_keys)
        
        # Report results
        if not missing and not extra:
            print(f"{Colors.GREEN}✓ All keys match! ({len(nl_keys)} keys){Colors.RESET}")
        else:
            has_errors = True
            
            if missing:
                print(f"\n{Colors.RED}Missing in English ({len(missing)}):{ Colors.RESET}")
                for key in missing:
                    print(f"  - {key}")
            
            if extra:
                print(f"\n{Colors.YELLOW}Extra in English ({len(extra)}):{ Colors.RESET}")
                for key in extra:
                    print(f"  - {key}")
        
        all_stats.append({
            'file': filename,
            'nl': len(nl_keys),
            'en': len(en_keys),
            'missing': len(missing),
            'extra': len(extra)
        })
    
    # Print summary
    if all_stats:
        print(f"\n{Colors.CYAN}Summary{Colors.RESET}")
        print("=" * 60)
        print("\nFile Statistics:")
        print("┌─────────────────────┬────────┬────────┬─────────┬───────┐")
        print("│ File                │ NL     │ EN     │ Missing │ Extra │")
        print("├─────────────────────┼────────┼────────┼─────────┼───────┤")
        
        total_nl = 0
        total_en = 0
        total_missing = 0
        total_extra = 0
        
        for stat in all_stats:
            print(f"│ {stat['file'][:19].ljust(19)} │ {str(stat['nl']).rjust(6)} │ {str(stat['en']).rjust(6)} │ {str(stat['missing']).rjust(7)} │ {str(stat['extra']).rjust(5)} │")
            
            total_nl += stat['nl']
            total_en += stat['en']
            total_missing += stat['missing']
            total_extra += stat['extra']
        
        print("├─────────────────────┼────────┼────────┼─────────┼───────┤")
        print(f"│ {Colors.CYAN}TOTAL{Colors.RESET}               │ {str(total_nl).rjust(6)} │ {str(total_en).rjust(6)} │ {str(total_missing).rjust(7)} │ {str(total_extra).rjust(5)} │")
        print("└─────────────────────┴────────┴────────┴─────────┴───────┘")
        
        print(f"\nTotal translation keys: {total_nl} (Dutch), {total_en} (English)")
        
        if total_missing > 0:
            print(f"{Colors.RED}Missing translations: {total_missing}{Colors.RESET}")
        
        if total_extra > 0:
            print(f"{Colors.YELLOW}Extra translations: {total_extra}{Colors.RESET}")
    
    # Return result
    if has_errors:
        print(f"\n{Colors.RED}✗ Translation check failed!{Colors.RESET}")
        return False
    else:
        print(f"\n{Colors.GREEN}✓ All translations are complete!{Colors.RESET}")
        return True

if __name__ == '__main__':
    success = check_translations()
    sys.exit(0 if success else 1)
