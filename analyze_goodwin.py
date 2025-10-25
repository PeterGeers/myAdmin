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
    query = "SELECT * FROM vw_mutaties WHERE Administration LIKE 'Goodwin%'"
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
    
    # Use Amount column from vw_mutaties
    amount_col = 'Amount'
    
    if amount_col:
        print(f"Total Transaction Amount: ${df[amount_col].sum():,.2f}")
        print(f"Average Transaction: ${df[amount_col].mean():.2f}")
    else:
        print("Amount column not found in data")
    print()
    
    # Account distribution
    print("=== ACCOUNT USAGE ===")
    account_usage = df['Reknum'].value_counts().head(10)
    parent_usage = df['Parent'].value_counts().head(10)
    
    print("Top Account Numbers (Reknum):")
    for account, count in account_usage.items():
        if pd.notna(account):
            account_name = df[df['Reknum'] == account]['AccountName'].iloc[0] if not df[df['Reknum'] == account].empty else 'Unknown'
            print(f"  {account} ({account_name}): {count} transactions")
    
    print("\nTop Parent Categories:")
    for parent, count in parent_usage.items():
        if pd.notna(parent):
            print(f"  {parent}: {count} transactions")
    print()
    
    # Transaction patterns
    print("=== TRANSACTION PATTERNS ===")
    
    # Convert TransactionDate to datetime if it's not already
    df['TransactionDate'] = pd.to_datetime(df['TransactionDate'])
    
    # Yearly summary
    yearly_summary = df.groupby('jaar').agg({
        'Amount': ['count', 'sum']
    }).round(2)
    print("Yearly Activity:")
    print(yearly_summary.tail(10))
    
    # Monthly summary for recent years
    recent_data = df[df['jaar'] >= 2020]
    if not recent_data.empty:
        monthly_summary = recent_data.groupby(['jaar', 'maand']).agg({
            'Amount': ['count', 'sum']
        }).round(2)
        print("\nMonthly Activity (2020+):")
        print(monthly_summary.tail(12))
    print()
    
    # Data quality issues
    print("=== DATA QUALITY FINDINGS ===")
    
    # Missing values
    missing_reknum = df['Reknum'].isna().sum()
    missing_ref = df['ReferenceNumber'].isna().sum()
    empty_description = (df['TransactionDescription'].isna() | (df['TransactionDescription'] == '')).sum()
    missing_aangifte = df['Aangifte'].isna().sum()
    
    print(f"Missing Account Numbers (Reknum): {missing_reknum}")
    print(f"Missing Reference Numbers: {missing_ref}")
    print(f"Empty Descriptions: {empty_description}")
    print(f"Missing Aangifte (Tax Category): {missing_aangifte}")
    
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
    
    cursor.close()
    conn.close()
    
    return df

def generate_recommendations(df):
    print("=== RECOMMENDATIONS ===")
    
    recommendations = []
    
    # Data quality recommendations
    missing_reknum = df['Reknum'].isna().sum()
    missing_aangifte = df['Aangifte'].isna().sum()
    
    if missing_reknum > 0:
        recommendations.append(f"1. Fix {missing_reknum} transactions with missing account numbers")
    
    if missing_aangifte > 0:
        recommendations.append(f"2. Add tax categories (Aangifte) to {missing_aangifte} transactions")
    
    # Duplicate recommendations
    dup_cols = ['TransactionDate', 'TransactionDescription', 'Amount']
    duplicates = df.duplicated(subset=dup_cols).sum()
    if duplicates > 0:
        recommendations.append(f"3. Review {duplicates} potential duplicate transactions")
    
    # Reference number recommendations
    missing_ref = df['ReferenceNumber'].isna().sum()
    if missing_ref > 0:
        recommendations.append(f"4. Add reference numbers to {missing_ref} transactions for better tracking")
    
    # Account code recommendations
    if 'Reknum' in df.columns:
        unusual_accounts = df[df['Reknum'].str.len() > 4]['Reknum'].nunique()
        if unusual_accounts > 0:
            recommendations.append("5. Review account codes longer than 4 digits for consistency")
    
    # Amount recommendations
    zero_amounts = (df['Amount'] == 0).sum()
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