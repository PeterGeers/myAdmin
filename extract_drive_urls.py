import re
import csv

# Read SQL file and extract records with drive.google.com
with open('finance20250903.sql', 'r', encoding='utf-8') as f:
    content = f.read()

# Find REPLACE INTO mutaties statements
pattern = r"REPLACE INTO `mutaties`.*?VALUES\s+(.*?)(?=\n\n|$)"
matches = re.findall(pattern, content, re.DOTALL)

results = []
for match in matches:
    # Split by "),(" to get individual records
    records = re.split(r'\),\s*\(', match)
    
    for record in records:
        # Check if contains mail.google
        if 'mail.google' in record:
            # Extract fields - mutaties has: id, TransactionNumber, Date, Description, Amount, Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4
            fields = re.findall(r"'([^']*)'|NULL|(\d+\.?\d*)", record)
            flat_fields = [f[0] if f[0] else f[1] for f in fields]
            
            if len(flat_fields) >= 12:
                id_val = flat_fields[0]
                ref3 = flat_fields[10] if len(flat_fields) > 10 else ''
                ref4 = flat_fields[11] if len(flat_fields) > 11 else ''
                
                if 'mail.google' in ref3:
                    results.append([id_val, ref3, ref4])

# Write to CSV
with open('gmail_urls_output.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'Ref3', 'Ref4'])
    writer.writerows(results)

print(f"Found {len(results)} records with mail.google.com URLs")
print(f"Output saved to gmail_urls_output.csv")
print("\nFirst 5 records:")
for i, row in enumerate(results[:5]):
    print(f"{row[0]}: {row[1][:80]}... | {row[2]}")
