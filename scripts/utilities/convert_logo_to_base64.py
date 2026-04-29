#!/usr/bin/env python3
"""Convert logo to base64 for embedding in HTML"""

import base64
from pathlib import Path

# Read the logo file
logo_path = Path('backend/static/jabaki-logo.png')

if not logo_path.exists():
    print(f"Logo not found at {logo_path}")
    exit(1)

with open(logo_path, 'rb') as f:
    logo_data = f.read()

# Convert to base64
base64_data = base64.b64encode(logo_data).decode('utf-8')

# Create data URL
data_url = f"data:image/png;base64,{base64_data}"

print("Base64 Data URL for logo:")
print("=" * 80)
print(data_url)
print("=" * 80)
print(f"\nLength: {len(data_url)} characters")
print("\nReplace the img src in templates with:")
print(f'<img src="{data_url[:100]}..." alt="Jabaki Logo" class="logo">')
