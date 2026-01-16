"""
Search OneDrive backup for missing invoice files
Reads missing_invoices.csv and searches local OneDrive folder for each unique Ref4 filename
Processes ALL records regardless of date
"""

import csv
import os
from pathlib import Path
from collections import defaultdict

# Configuration
MISSING_INVOICES_CSV = 'missing_invoices.csv'
ONEDRIVE_BACKUP_PATH = r'C:\Users\peter\OneDrive\Admin\reports'
OUTPUT_FOUND_CSV = 'found_invoices.csv'
OUTPUT_NOT_FOUND_CSV = 'not_found_invoices.csv'

def load_missing_invoices(csv_file):
    """Load missing invoices and group by Ref4 filename"""
    invoices_by_ref4 = defaultdict(list)
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref4 = row.get('Ref4', '').strip()
            if ref4:
                invoices_by_ref4[ref4].append(row)
    
    return invoices_by_ref4

def search_file_in_onedrive(filename, base_path):
    """
    Search for a file in OneDrive backup folder (recursive)
    Returns full path if found, None otherwise
    """
    base_path = Path(base_path)
    
    if not base_path.exists():
        print(f"⚠️  OneDrive path does not exist: {base_path}")
        return None
    
    # Search recursively
    for file_path in base_path.rglob(filename):
        if file_path.is_file():
            return str(file_path)
    
    # Try case-insensitive search
    filename_lower = filename.lower()
    for file_path in base_path.rglob('*'):
        if file_path.is_file() and file_path.name.lower() == filename_lower:
            return str(file_path)
    
    return None

def main():
    print("Searching OneDrive for missing invoices...")
    print(f"OneDrive path: {ONEDRIVE_BACKUP_PATH}")
    print()
    
    # Load missing invoices
    invoices_by_ref4 = load_missing_invoices(MISSING_INVOICES_CSV)
    unique_files = list(invoices_by_ref4.keys())
    
    print(f"Total unique filenames to search: {len(unique_files)}")
    print(f"Total invoice records: {sum(len(records) for records in invoices_by_ref4.values())}")
    print()
    
    # Search results
    found = []
    not_found = []
    
    for idx, ref4 in enumerate(unique_files, 1):
        print(f"[{idx}/{len(unique_files)}] Searching: {ref4}...", end=' ')
        
        file_path = search_file_in_onedrive(ref4, ONEDRIVE_BACKUP_PATH)
        
        if file_path:
            print(f"FOUND")
            for record in invoices_by_ref4[ref4]:
                found.append({
                    'ID': record['ID'],
                    'Date': record['Date'],
                    'ReferenceNumber': record['ReferenceNumber'],
                    'Ref4': ref4,
                    'OneDrivePath': file_path
                })
        else:
            print(f"NOT FOUND")
            for record in invoices_by_ref4[ref4]:
                not_found.append({
                    'ID': record['ID'],
                    'Date': record['Date'],
                    'ReferenceNumber': record['ReferenceNumber'],
                    'Ref4': ref4
                })
    
    # Write results
    print()
    print("Writing results...")
    
    with open(OUTPUT_FOUND_CSV, 'w', newline='', encoding='utf-8') as f:
        if found:
            writer = csv.DictWriter(f, fieldnames=['ID', 'Date', 'ReferenceNumber', 'Ref4', 'OneDrivePath'])
            writer.writeheader()
            writer.writerows(found)
    
    with open(OUTPUT_NOT_FOUND_CSV, 'w', newline='', encoding='utf-8') as f:
        if not_found:
            writer = csv.DictWriter(f, fieldnames=['ID', 'Date', 'ReferenceNumber', 'Ref4'])
            writer.writeheader()
            writer.writerows(not_found)
    
    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Found: {len(found)} records")
    print(f"Not found: {len(not_found)} records")
    print(f"Found invoices saved to: {OUTPUT_FOUND_CSV}")
    print(f"Not found invoices saved to: {OUTPUT_NOT_FOUND_CSV}")
    print("=" * 60)

if __name__ == '__main__':
    main()
