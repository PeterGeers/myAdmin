"""
Sample Financial Data Generator

This script generates sample financial data for testing the financial report template.
It creates realistic data structures that match the expected format for the template.
"""

from datetime import datetime, timedelta
import json
import random


def generate_sample_financial_data(
    administration="GoodwinSolutions",
    start_date="2026-01-01",
    end_date="2026-03-31",
    generated_by="test@example.com"
):
    """
    Generate sample financial data for testing.
    
    Args:
        administration: Tenant/administration name
        start_date: Report period start date (YYYY-MM-DD)
        end_date: Report period end date (YYYY-MM-DD)
        generated_by: User who generated the report
        
    Returns:
        Dictionary with complete financial data structure
    """
    
    # Revenue categories
    revenue_categories = [
        {"account": "4000", "account_name": "Sales Revenue", "amount": 120000.00},
        {"account": "4100", "account_name": "Service Revenue", "amount": 30000.00},
        {"account": "8000", "account_name": "Interest Income", "amount": 500.00}
    ]
    revenue_total = sum(cat["amount"] for cat in revenue_categories)
    
    # Operating expenses
    operating_expense_categories = [
        {"account": "6000", "account_name": "Salaries & Wages", "amount": 60000.00},
        {"account": "6100", "account_name": "Rent", "amount": 15000.00},
        {"account": "6200", "account_name": "Utilities", "amount": 3000.00},
        {"account": "6300", "account_name": "Office Supplies", "amount": 2000.00},
        {"account": "6400", "account_name": "Marketing", "amount": 5000.00}
    ]
    operating_expenses_total = sum(cat["amount"] for cat in operating_expense_categories)
    
    # Other expenses
    other_expense_categories = [
        {"account": "7000", "account_name": "Interest Expense", "amount": 2000.00},
        {"account": "7100", "account_name": "Depreciation", "amount": 3000.00}
    ]
    other_expenses_total = sum(cat["amount"] for cat in other_expense_categories)
    
    expenses_total = operating_expenses_total + other_expenses_total
    
    # VAT
    vat_payable = 15000.00
    vat_receivable = 10000.00
    vat_net = vat_payable - vat_receivable
    
    # Net income
    net_income = revenue_total - expenses_total - vat_net
    
    # Bank accounts
    bank_accounts = [
        {"account": "1000", "account_name": "Main Bank Account", "balance": 45000.00},
        {"account": "1010", "account_name": "Savings Account", "balance": 25000.00}
    ]
    current_assets_total = sum(acc["balance"] for acc in bank_accounts)
    
    # Fixed assets
    fixed_assets_categories = [
        {"account": "0100", "account_name": "Equipment", "amount": 50000.00},
        {"account": "0200", "account_name": "Furniture", "amount": 15000.00},
        {"account": "0300", "account_name": "Vehicles", "amount": 35000.00}
    ]
    fixed_assets_total = sum(cat["amount"] for cat in fixed_assets_categories)
    
    assets_total = current_assets_total + fixed_assets_total
    
    # Current liabilities
    current_liabilities_categories = [
        {"account": "2000", "account_name": "Accounts Payable", "amount": 15000.00},
        {"account": "2010", "account_name": "VAT Payable", "amount": vat_net},
        {"account": "2100", "account_name": "Short-term Loan", "amount": 10000.00}
    ]
    current_liabilities_total = sum(cat["amount"] for cat in current_liabilities_categories)
    
    # Long-term liabilities
    long_term_liabilities_categories = [
        {"account": "3000", "account_name": "Long-term Loan", "amount": 40000.00},
        {"account": "3100", "account_name": "Mortgage", "amount": 60000.00}
    ]
    long_term_liabilities_total = sum(cat["amount"] for cat in long_term_liabilities_categories)
    
    liabilities_total = current_liabilities_total + long_term_liabilities_total
    
    # Equity
    equity_total = assets_total - liabilities_total
    equity_categories = [
        {"account": "9000", "account_name": "Owner's Equity", "amount": equity_total - net_income},
        {"account": "9100", "account_name": "Retained Earnings", "amount": net_income}
    ]
    
    # Account details (sample)
    account_details = [
        {
            "account": "1000",
            "account_name": "Main Bank Account",
            "parent": "Current Assets",
            "debit": 150000.00,
            "credit": 105000.00,
            "balance": 45000.00
        },
        {
            "account": "4000",
            "account_name": "Sales Revenue",
            "parent": "Revenue",
            "debit": 0.00,
            "credit": 120000.00,
            "balance": -120000.00
        },
        {
            "account": "6000",
            "account_name": "Salaries & Wages",
            "parent": "Operating Expenses",
            "debit": 60000.00,
            "credit": 0.00,
            "balance": 60000.00
        }
    ]
    
    # Sample transactions
    transactions_list = []
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    transaction_templates = [
        ("Invoice payment received", "1000", "Main Bank Account", 5000.00, 0.00, "INV-{:04d}"),
        ("Salary payment", "6000", "Salaries & Wages", 0.00, 5000.00, "SAL-{:04d}"),
        ("Rent payment", "6100", "Rent", 0.00, 5000.00, "RENT-{:04d}"),
        ("Sales invoice", "4000", "Sales Revenue", 0.00, 10000.00, "SALE-{:04d}")
    ]
    
    transaction_count = 0
    while current_date <= end and transaction_count < 50:
        template = random.choice(transaction_templates)
        description, account, account_name, debit, credit, ref_pattern = template
        
        transactions_list.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "description": description,
            "account": account,
            "account_name": account_name,
            "debit": debit,
            "credit": credit,
            "reference": ref_pattern.format(transaction_count + 1)
        })
        
        current_date += timedelta(days=random.randint(1, 5))
        transaction_count += 1
    
    # Build complete data structure
    data = {
        "metadata": {
            "title": f"Financial Report {administration}",
            "administration": administration,
            "period": {
                "start_date": start_date,
                "end_date": end_date
            },
            "generated_date": datetime.now().strftime("%Y-%m-%d"),
            "generated_by": generated_by
        },
        "summary": {
            "total_revenue": revenue_total,
            "total_expenses": expenses_total,
            "net_income": net_income,
            "total_assets": assets_total,
            "total_liabilities": liabilities_total,
            "equity": equity_total
        },
        "profit_loss": {
            "revenue": {
                "categories": revenue_categories,
                "total": revenue_total
            },
            "expenses": {
                "operating": {
                    "categories": operating_expense_categories,
                    "total": operating_expenses_total
                },
                "other": {
                    "categories": other_expense_categories,
                    "total": other_expenses_total
                },
                "total": expenses_total
            },
            "vat": {
                "payable": vat_payable,
                "receivable": vat_receivable,
                "net": vat_net
            }
        },
        "balance_sheet": {
            "assets": {
                "current": {
                    "bank_accounts": bank_accounts,
                    "total": current_assets_total
                },
                "fixed": {
                    "categories": fixed_assets_categories,
                    "total": fixed_assets_total
                },
                "total": assets_total
            },
            "liabilities": {
                "current": {
                    "categories": current_liabilities_categories,
                    "total": current_liabilities_total
                },
                "long_term": {
                    "categories": long_term_liabilities_categories,
                    "total": long_term_liabilities_total
                },
                "total": liabilities_total
            },
            "equity": {
                "categories": equity_categories,
                "total": equity_total
            }
        },
        "account_details": {
            "accounts": account_details
        },
        "transactions": {
            "list": transactions_list,
            "count": len(transactions_list)
        }
    }
    
    return data


def save_sample_data_to_file(filename="sample_financial_data.json"):
    """Generate and save sample data to JSON file."""
    data = generate_sample_financial_data()
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Sample data saved to {filename}")
    return data


if __name__ == "__main__":
    # Generate sample data for both tenants
    print("Generating sample financial data...")
    
    # GoodwinSolutions
    data_goodwin = generate_sample_financial_data(
        administration="GoodwinSolutions",
        start_date="2026-01-01",
        end_date="2026-03-31"
    )
    with open("sample_financial_data_goodwin.json", 'w', encoding='utf-8') as f:
        json.dump(data_goodwin, f, indent=2, ensure_ascii=False)
    print("✓ Generated sample_financial_data_goodwin.json")
    
    # PeterPrive
    data_peter = generate_sample_financial_data(
        administration="PeterPrive",
        start_date="2026-01-01",
        end_date="2026-03-31"
    )
    with open("sample_financial_data_peter.json", 'w', encoding='utf-8') as f:
        json.dump(data_peter, f, indent=2, ensure_ascii=False)
    print("✓ Generated sample_financial_data_peter.json")
    
    print("\nSample data generation complete!")
    print("\nSummary:")
    print(f"  Revenue: € {data_goodwin['summary']['total_revenue']:,.2f}")
    print(f"  Expenses: € {data_goodwin['summary']['total_expenses']:,.2f}")
    print(f"  Net Income: € {data_goodwin['summary']['net_income']:,.2f}")
    print(f"  Total Assets: € {data_goodwin['summary']['total_assets']:,.2f}")
    print(f"  Total Liabilities: € {data_goodwin['summary']['total_liabilities']:,.2f}")
    print(f"  Equity: € {data_goodwin['summary']['equity']:,.2f}")
