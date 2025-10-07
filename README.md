# PDF Transaction Processor

A ReactJS SPA with Python backend for processing PDF files, extracting transactions, and storing them in MySQL.

## Setup

### Frontend
```bash
cd frontend
npm install
npm start
```

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your database credentials
python app.py
```

### Google Drive Setup
1. Create a Google Cloud project
2. Enable Google Drive API
3. Download credentials.json to backend folder
4. Run the app and authenticate when prompted

### Database Setup
```sql
CREATE DATABASE transactions_db;
```

## Features
- PDF file upload to Google Drive
- Automatic PDF parsing and transaction extraction
- Editable transaction data before saving
- MySQL storage with transaction metadata