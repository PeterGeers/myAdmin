#!/usr/bin/env python3
"""
Clean up duplicate tab comments in myAdminReports.tsx
"""
import re

def cleanup_comments():
    file_path = 'frontend/src/components/myAdminReports.tsx'
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to find duplicate comments (two consecutive {/* ... Tab */} lines)
    pattern = r'(\s*\{/\* .* Tab \*/\})\s*\{/\* .* Tab \*/\}'
    
    # Replace with just the first comment
    content = re.sub(pattern, r'\1', content)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Cleaned up duplicate comments in {file_path}")

if __name__ == '__main__':
    cleanup_comments()
