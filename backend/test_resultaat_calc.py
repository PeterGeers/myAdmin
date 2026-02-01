"""Test resultaat calculation logic."""

# Simulate the data
report_data = [
    {'Parent': '1000', 'Aangifte': 'Liquide middelen', 'Amount': 88262.80},
    {'Parent': '1000', 'Aangifte': 'kortlopende schulden', 'Amount': -132.73},
    {'Parent': '1000', 'Aangifte': 'vorderingen', 'Amount': 0.00},
    {'Parent': '2000', 'Aangifte': 'BTW', 'Amount': -1430.31},
    {'Parent': '2000', 'Aangifte': 'Toeristenbelasting', 'Amount': 0.00},
    {'Parent': '2000', 'Aangifte': 'Tussenrekening', 'Amount': 0.00},
    {'Parent': '3000', 'Aangifte': 'Financiële vaste activa', 'Amount': 79153.43},
    {'Parent': '3000', 'Aangifte': 'Materiële vaste activa', 'Amount': 33884.56},
    {'Parent': '3000', 'Aangifte': 'Ondernemingsvermogen', 'Amount': -228591.51},
    {'Parent': '4000', 'Aangifte': 'Andere kosten', 'Amount': 34958.68},
    {'Parent': '4000', 'Aangifte': 'Auto- en transportkosten', 'Amount': 1923.79},
    {'Parent': '4000', 'Aangifte': 'Huisvestingskosten', 'Amount': 70000.00},
    {'Parent': '4000', 'Aangifte': 'Verkoopkosten', 'Amount': 12106.75},
    {'Parent': '8000', 'Aangifte': 'Bijzondere baten en lasten', 'Amount': -1862.91},
    {'Parent': '8000', 'Aangifte': 'opbrengsten', 'Amount': -88272.55},
]

# Calculate resultaat using the generator logic
resultaat = sum(
    float(item.get('Amount', 0)) 
    for item in report_data 
    if item.get('Parent', '').startswith(('4', '5', '6', '7', '8', '9'))
)

print(f"Report data items: {len(report_data)}")
print(f"\nP&L items (Parent 4000+):")
for item in report_data:
    if item.get('Parent', '').startswith(('4', '5', '6', '7', '8', '9')):
        print(f"  {item['Parent']} | {item['Aangifte']:30s} | €{item['Amount']:15,.2f}")

print(f"\nRESULTAAT: €{resultaat:,.2f}")
print(f"abs(resultaat) >= 0.01: {abs(resultaat) >= 0.01}")
