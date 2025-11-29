import mysql.connector
from dotenv import load_dotenv
import os
import csv
import re
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

load_dotenv('backend/.env')

# Google Drive API setup
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_drive_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('backend/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('drive', 'v3', credentials=creds)

def extract_file_id(url):
    """Extract file/folder ID from Google Drive/Gmail URL"""
    # Drive file: /file/d/FILE_ID/
    match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1), 'drive'
    
    # Drive folder: /folders/FOLDER_ID
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1), 'drive'
    
    # Gmail: mail.google.com
    if 'mail.google' in url:
        return None, 'gmail'
    
    return None, None

def check_drive_file(service, file_id):
    """Check if Drive file exists"""
    try:
        service.files().get(fileId=file_id, fields='id').execute()
        return True
    except:
        return False

# Connect to database
db = mysql.connector.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    user=os.getenv('DB_USER', 'root'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME', 'finance')
)

cursor = db.cursor(dictionary=True)

# Get only Drive URLs (exclude Gmail and Docs)
cursor.execute("""
    SELECT ID, TransactionDate, ReferenceNumber, Ref3, Ref4 
    FROM mutaties 
    WHERE Ref3 LIKE '%drive.google.com%'
    ORDER BY ID
""")

records = cursor.fetchall()
print(f"Found {len(records)} records with Drive URLs")

# Initialize Drive API
print("Connecting to Google Drive API...")
service = get_drive_service()

# Check URLs
missing = []
checked = 0

print("Checking URLs...")
total = len(records)

for record in records:
    checked += 1
    file_id, url_type = extract_file_id(record['Ref3'])
    
    print(f"[{checked}/{total}] {record['TransactionDate']} ID {record['ID']}...", end=' ')
    
    if file_id:
        exists = check_drive_file(service, file_id)
        if not exists:
            missing.append(record)
            print(f"MISSING: {record['Ref4']}")
        else:
            print("OK")
    else:
        print("Invalid URL")

# Write missing invoices to CSV
with open('missing_invoices.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['ID', 'Date', 'ReferenceNumber', 'Ref3', 'Ref4'])
    
    for rec in missing:
        writer.writerow([
            rec['ID'],
            rec['TransactionDate'],
            rec['ReferenceNumber'],
            rec['Ref3'],
            rec['Ref4']
        ])

print(f"\nDone!")
print(f"Total checked: {len(records)}")
print(f"Missing: {len(missing)}")
print(f"Output: missing_invoices.csv")

cursor.close()
db.close()
