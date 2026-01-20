#!/usr/bin/env python3
"""
Analyze Goodwin administration data from vw_mutaties view
"""

import mysql.connector
import os
from dotenv import load_dotenv
from collections import defaultdict, Counter
from datetime import datetime
import pandas as pd

load_dotenv('backend/.env')

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'finance')
    )

def analyze_goodwin_data():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Query Goodwin administration data
    query = "SELECT * FROM mutaties WHERE Administration LIKE 'Goodwin%'"
    cursor.execute(query)
    results = cursor.fetchall()
    
    if not results:
        print("No Goodwin administration data found.")
        return
    
    print(f"=== GOODWIN ADMINISTRATION ANALYSIS ===")
    print(f"Total Records: {len(results)}")
    print()
    
    # Convert to DataFrame for easier analysis
    df = pd.DataFrame(results)
    
    # Basic statistics
    print("=== BASIC STATISTICS ===")
    print(f"Date Range: {df['TransactionDate'].min()} to {df['TransactionDate'].max()}")
    
    # Use TransactionAmount column from mutaties table
    amount_col = 'TransactionAmount'
    
    if amount_col in df.columns:
        print(f"Total Transaction Amount: ${df[amount_col].sum():,.2f}")
        print(f"Average Transaction: ${df[amount_col].mean():.2f}")
    else:
        print("TransactionAmount column not found in data")
    print()
    
    # Account distribution
    print("=== ACCOUNT USAGE ===")
    debet_usage = df['Debet'].value_counts().head(10)
    credit_usage = df['Credit'].value_counts().head(10)
    
    print("Top Debet Accounts:")
    for account, count in debet_usage.items():
        if pd.notna(account):
            print(f"  {account}: {count} transactions")
    
    print("\nTop Credit Accounts:")
    for account, count in credit_usage.items():
        if pd.notna(account):
            print(f"  {account}: {count} transactions")
    print()
    
    # Transaction patterns
    print("=== TRANSACTION PATTERNS ===")
    
    # Convert TransactionDate to datetime if it's not already
    df['TransactionDate'] = pd.to_datetime(df['TransactionDate'])
    
    # Yearly summary
    df['Year'] = df['TransactionDate'].dt.year
    df['Month'] = df['TransactionDate'].dt.month
    yearly_summary = df.groupby('Year').agg({
        amount_col: ['count', 'sum']
    }).round(2)
    print("Yearly Activity:")
    print(yearly_summary.tail(10))
    
    # Monthly summary for recent years
    recent_data = df[df['Year'] >= 2020]
    if not recent_data.empty:
        monthly_summary = recent_data.groupby(['Year', 'Month']).agg({
            amount_col: ['count', 'sum']
        }).round(2)
        print("\nMonthly Activity (2020+):")
        print(monthly_summary.tail(12))
    print()
    
    # Data quality issues
    print("=== DATA QUALITY FINDINGS ===")
    
    # Missing values
    missing_debet = df['Debet'].isna().sum()
    missing_credit = df['Credit'].isna().sum()
    missing_ref = df['ReferenceNumber'].isna().sum()
    empty_description = (df['TransactionDescription'].isna() | (df['TransactionDescription'] == '')).sum()
    
    print(f"Missing Debet Accounts: {missing_debet}")
    print(f"Missing Credit Accounts: {missing_credit}")
    print(f"Missing Reference Numbers: {missing_ref}")
    print(f"Empty Descriptions: {empty_description}")
    
    # Duplicate detection
    dup_cols = ['TransactionDate', 'TransactionDescription']
    if amount_col:
        dup_cols.append(amount_col)
    duplicates = df.duplicated(subset=dup_cols).sum()
    print(f"Potential Duplicates: {duplicates}")
    
    # Unusual amounts
    if amount_col:
        zero_amounts = (df[amount_col] == 0).sum()
        negative_amounts = (df[amount_col] < 0).sum()
        large_amounts = (df[amount_col] > 10000).sum()
        
        print(f"Zero Amount Transactions: {zero_amounts}")
        print(f"Negative Amounts: {negative_amounts}")
        print(f"Large Amounts (>$10k): {large_amounts}")
    else:
        print("Amount analysis skipped - no amount column found")
    print()
    
    # Reference number patterns
    print("=== REFERENCE NUMBER ANALYSIS ===")
    ref_patterns = df['ReferenceNumber'].value_counts().head(10)
    print("Most Common Reference Numbers:")
    for ref, count in ref_patterns.items():
        if pd.notna(ref) and ref != '':
            print(f"  {ref}: {count} times")
    print()
    
    # Show duplicate transactions if any
    dup_cols = ['TransactionDate', 'TransactionDescription', 'TransactionAmount', 'Debet', 'Credit']
    duplicates_mask = df.duplicated(subset=dup_cols, keep=False)
    if duplicates_mask.sum() > 0:
        print("=== DUPLICATE TRANSACTIONS ===")
        duplicate_transactions = df[duplicates_mask].sort_values(dup_cols)
        for _, row in duplicate_transactions.iterrows():
            print(f"ID: {row['ID']} | Date: {row['TransactionDate']} | Amount: ${row['TransactionAmount']:.2f} | Debet: {row['Debet']} | Credit: {row['Credit']} | Desc: {row['TransactionDescription'][:30]}...")
        print()
    
    # Show transactions missing reference numbers
    missing_ref_mask = df['ReferenceNumber'].isna() | (df['ReferenceNumber'] == '')
    if missing_ref_mask.sum() > 0:
        print("=== TRANSACTIONS MISSING REFERENCE NUMBERS ===")
        missing_ref_transactions = df[missing_ref_mask].sort_values('TransactionDate')
        for _, row in missing_ref_transactions.iterrows():
            print(f"ID: {row['ID']} | Date: {row['TransactionDate']} | Amount: ${row['TransactionAmount']:.2f} | Debet: {row['Debet']} | Credit: {row['Credit']} | Desc: {row['TransactionDescription'][:40]}...")
        print()
    
    cursor.close()
    conn.close()
    
    return df

def generate_recommendations(df):
    print("=== RECOMMENDATIONS ===")
    
    recommendations = []
    
    # Data quality recommendations
    missing_debet = df['Debet'].isna().sum()
    missing_credit = df['Credit'].isna().sum()
    
    if missing_debet > 0:
        recommendations.append(f"1. Fix {missing_debet} transactions with missing debet accounts")
    
    if missing_credit > 0:
        recommendations.append(f"2. Fix {missing_credit} transactions with missing credit accounts")
    
    # Duplicate recommendations
    dup_cols = ['TransactionDate', 'TransactionDescription', 'TransactionAmount', 'Debet', 'Credit']
    duplicates = df.duplicated(subset=dup_cols).sum()
    if duplicates > 0:
        recommendations.append(f"3. Review {duplicates} potential duplicate transactions")
    
    # Reference number recommendations
    missing_ref = df['ReferenceNumber'].isna().sum()
    if missing_ref > 0:
        recommendations.append(f"4. Add reference numbers to {missing_ref} transactions for better tracking")
    
    # Account code recommendations
    if 'Debet' in df.columns:
        unusual_debet = df[df['Debet'].str.len() > 4]['Debet'].nunique() if df['Debet'].dtype == 'object' else 0
        if unusual_debet > 0:
            recommendations.append("5. Review debet account codes longer than 4 digits for consistency")
    
    # Amount recommendations
    zero_amounts = (df['TransactionAmount'] == 0).sum()
    if zero_amounts > 0:
        recommendations.append(f"6. Investigate {zero_amounts} zero-amount transactions")
    
    # Pattern recommendations
    single_use_refs = df['ReferenceNumber'].value_counts()
    single_refs = (single_use_refs == 1).sum()
    if single_refs > len(single_use_refs) * 0.8:
        recommendations.append("7. Consider standardizing reference number patterns for better reporting")
    
    for rec in recommendations:
        print(rec)
    
    if not recommendations:
        print("Data quality appears good - no major issues found!")

if __name__ == "__main__":
    try:
        df = analyze_goodwin_data()
        if df is not None:
            generate_recommendations(df)
    except Exception as e:
        print(f"Error analyzing data: {e}")