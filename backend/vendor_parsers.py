import re
from datetime import datetime
from database import DatabaseManager

class VendorParsers:
    def parse_booking(self, lines):
        """Parse Booking.com invoices based on R script logic"""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'Booking.com invoice',
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'accommodation_number': '',
            'invoice_number': '',
            'accommodation_name': '',
            'commission_type': ''
        }
        
        for line in lines:
            line_lower = line.lower()
            
            # Extract date (Datum:|Date:)
            if 'datum:' in line_lower or 'date:' in line_lower:
                date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
                if date_match:
                    date_str = date_match.group(1)
                    try:
                        # Convert DD/MM/YYYY to YYYY-MM-DD
                        day, month, year = date_str.split('/')
                        data['date'] = f"{year}-{month}-{day}"
                    except:
                        pass
            
            # Extract total amount (Totaal EUR|Total amount due EUR)
            if 'totaal eur' in line_lower or 'total amount due eur' in line_lower:
                amount_match = re.search(r'eur\s+(\d+[,.]\d+)', line_lower)
                if amount_match:
                    data['total_amount'] = float(amount_match.group(1).replace(',', '.'))
            
            # Extract VAT amount (VAT|BTW)
            if ('vat' in line_lower or 'btw' in line_lower) and 'eur' in line_lower:
                vat_match = re.search(r'eur\s+(\d+[,.]\d+)', line_lower)
                if vat_match:
                    data['vat_amount'] = float(vat_match.group(1).replace(',', '.'))
            
            # Extract accommodation number
            if 'accommodation number:' in line_lower or 'accommodatie id:' in line_lower:
                accom_match = re.search(r'(\d+)', line)
                if accom_match:
                    data['accommodation_number'] = accom_match.group(1)
            
            # Extract invoice number
            if 'invoice number:' in line_lower or 'factuurnummer:' in line_lower:
                invoice_match = re.search(r'(\d+)', line)
                if invoice_match:
                    data['invoice_number'] = invoice_match.group(1)
            
            # Extract commission type from Description line
            if 'description:' in line_lower and 'room sales commission' in line_lower:
                data['commission_type'] = 'Room Sales Commission'
        
        # Calculate VAT if not found (21% of total/121*21)
        if data['vat_amount'] == 0 and data['total_amount'] > 0:
            data['vat_amount'] = round((data['total_amount'] / 121) * 21, 2)
        
        # Lookup accommodation name from database
        if data['accommodation_number']:
            try:
                db = DatabaseManager()
                bnb_lookup = db.get_bnb_lookup('bdc')
                for entry in bnb_lookup:
                    if str(entry.get('id', '')) == data['accommodation_number']:
                        data['accommodation_name'] = entry.get('name', '')
                        break
            except Exception as e:
                print(f"Error looking up accommodation name: {e}")
        
        # Build description with accommodation name and commission type
        desc_parts = []
        if data['accommodation_name']:
            desc_parts.append(data['accommodation_name'])
        elif data['accommodation_number']:
            desc_parts.append(f"Accommodation {data['accommodation_number']}")
        
        if data['invoice_number']:
            desc_parts.append(data['invoice_number'])
        
        if data['commission_type']:
            desc_parts.append(data['commission_type'])
        
        desc_parts.append(data['date'])
        data['description'] = ' '.join(desc_parts)
        
        return data
    
    def parse_avance(self, lines):
        """Parse Avance invoices"""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'Avance invoice',
            'total_amount': 0.0,
            'vat_amount': 0.0
        }
        
        for line in lines:
            # Look for amounts
            amount_match = re.search(r'€?\s*(\d+[,.]?\d*)', line)
            if amount_match:
                amount = float(amount_match.group(1).replace(',', '.'))
                if data['total_amount'] == 0:
                    data['total_amount'] = amount
        
        return data
    
    def parse_action(self, lines):
        return {'date': datetime.now().strftime('%Y-%m-%d'), 'description': 'Action invoice', 'total_amount': 0.0}
    
    def parse_mastercard(self, lines):
        return {'date': datetime.now().strftime('%Y-%m-%d'), 'description': 'Mastercard transaction', 'total_amount': 0.0}
    
    def parse_visa(self, lines):
        return {'date': datetime.now().strftime('%Y-%m-%d'), 'description': 'Visa transaction', 'total_amount': 0.0}
    
    def parse_bolcom(self, lines):
        return {'date': datetime.now().strftime('%Y-%m-%d'), 'description': 'Bol.com order', 'total_amount': 0.0}
    
    def parse_picnic(self, lines):
        return {'date': datetime.now().strftime('%Y-%m-%d'), 'description': 'Picnic order', 'total_amount': 0.0}
    
    def parse_netflix(self, lines):
        """Parse Netflix invoices"""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'Netflix subscription',
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'subscription_period': '',
            'receipt_number': ''
        }
        
        print(f"Netflix parser processing {len(lines)} lines", flush=True)
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            print(f"Line {i}: {line}", flush=True)
            
            # Extract receipt number: "Receipt No. 94822-1FD20-77BF4-18517"
            if 'receipt no.' in line_lower:
                receipt_match = re.search(r'receipt no\.\s*([A-Z0-9\-]+)', line, re.IGNORECASE)
                if receipt_match:
                    data['receipt_number'] = receipt_match.group(1)
                    print(f"Found receipt number: {data['receipt_number']}", flush=True)
            
            # Look for header line "Date Description Service Period Amount VAT % VAT Total"
            if ('date' in line_lower and 'description' in line_lower and 
                ('service' in line_lower or 'p eriod' in line_lower)):
                print(f"Found header line at {i}: {line}", flush=True)
                # Check next line for data: "17/09/2025 Streaming Service 17/09/2025–16/10/2025 €15.69 21% €3.30 €18.99"
                if i + 1 < len(lines):
                    data_line = lines[i + 1]
                    print(f"Processing data line: {data_line}", flush=True)
                    
                    # Extract first date (DD/MM/YYYY format)
                    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', data_line)
                    if date_match:
                        date_str = date_match.group(1)
                        print(f"Found date: {date_str}", flush=True)
                        try:
                            # Convert DD/MM/YYYY to YYYY-MM-DD
                            day, month, year = date_str.split('/')
                            data['date'] = f"{year}-{month}-{day}"
                        except:
                            pass
                    
                    # Extract amounts: €15.69 (net), €3.30 (VAT), €18.99 (total)
                    amounts = re.findall(r'€([\d,\.]+)', data_line)
                    print(f"Found amounts: {amounts}", flush=True)
                    if len(amounts) >= 3:
                        try:
                            net_amount = float(amounts[0].replace(',', '.'))
                            data['vat_amount'] = float(amounts[1].replace(',', '.'))
                            data['total_amount'] = float(amounts[2].replace(',', '.'))
                            print(f"Parsed amounts - Net: {net_amount}, VAT: {data['vat_amount']}, Total: {data['total_amount']}", flush=True)
                        except Exception as e:
                            print(f"Error parsing amounts: {e}", flush=True)
                    
                    # Extract service period for description
                    period_match = re.search(r'(\d{2}/\d{2}/\d{4}–\d{2}/\d{2}/\d{4})', data_line)
                    if period_match:
                        data['subscription_period'] = period_match.group(1)
                    
                    # Build description with receipt number and period
                    desc_parts = ["Netflix Streaming Service"]
                    if data['subscription_period']:
                        desc_parts.append(data['subscription_period'])
                    if data['receipt_number']:
                        desc_parts.append(f"Receipt No. {data['receipt_number']}")
                    
                    data['description'] = ' '.join(desc_parts)
                    print(f"Built description: {data['description']}", flush=True)
                    
                    break
        
        print(f"Final Netflix data: {data}", flush=True)
        return data
    
    def parse_temu(self, lines):
        return {'date': datetime.now().strftime('%Y-%m-%d'), 'description': 'Temu order', 'total_amount': 0.0}
    
    def parse_ziggo(self, lines):
        return {'date': datetime.now().strftime('%Y-%m-%d'), 'description': 'Ziggo service', 'total_amount': 0.0}
    
    def parse_coursera(self, lines):
        """Parse Coursera invoices"""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'Coursera subscription',
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'order_number': '',
            'product_details': ''
        }
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Extract VAT amount: VAT (EUR): 7.12
            if 'vat (eur):' in line_lower:
                vat_match = re.search(r'vat \(eur\):\s*([\d,\.]+)', line_lower)
                if vat_match:
                    data['vat_amount'] = float(vat_match.group(1).replace(',', '.'))
            
            # Extract total amount: TOTAL (EUR): 41.00
            if 'total (eur):' in line_lower:
                total_match = re.search(r'total \(eur\):\s*([\d,\.]+)', line_lower)
                if total_match:
                    data['total_amount'] = float(total_match.group(1).replace(',', '.'))
            
            # Extract order number: Order Number: 405249340
            if 'order number:' in line_lower:
                order_match = re.search(r'order number:\s*(\d+)', line_lower)
                if order_match:
                    data['order_number'] = order_match.group(1)
            
            # Extract product details (line after "Product Details Price Qty")
            if 'product details' in line_lower and 'price' in line_lower and 'qty' in line_lower:
                if i + 1 < len(lines):
                    data['product_details'] = lines[i + 1].strip()
            
            # Extract date (line after "Mountain View, CA 94041 USA")
            if 'mountain view' in line_lower and 'ca 94041 usa' in line_lower:
                if i + 1 < len(lines):
                    date_line = lines[i + 1].strip()
                    # Look for date patterns like MM/DD/YYYY or Month DD, YYYY
                    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', date_line)
                    if date_match:
                        date_str = date_match.group(1)
                        try:
                            # Convert MM/DD/YYYY to YYYY-MM-DD
                            month, day, year = date_str.split('/')
                            data['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        except:
                            pass
        
        # Build description with order number and product details
        desc_parts = []
        if data['order_number']:
            desc_parts.append(f"Order Number: {data['order_number']}")
        if data['product_details']:
            desc_parts.append(data['product_details'])
        
        if desc_parts:
            data['description'] = ' '.join(desc_parts)
        
        return data
    
    def parse_btw(self, lines):
        """Parse BTW invoices - government VAT payments have no additional VAT"""
        print(f"BTW: Processing {len(lines)} lines", flush=True)
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'BTW invoice',
            'total_amount': 0.0,
            'vat_amount': 0.0,  # Always 0 for BTW payments to government
            'btw_number': '',
            'invoice_number': '',
            'vendor_name': '',
            'aangiftenummer': '',
            'betalingskenmerk': ''
        }
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Extract BTW number: BTW: NL123456789B01
            if 'btw' in line_lower and re.search(r'[a-z]{2}\d{9}b\d{2}', line_lower):
                btw_match = re.search(r'([a-z]{2}\d{9}b\d{2})', line_lower)
                if btw_match:
                    data['btw_number'] = btw_match.group(1).upper()
            
            # Extract invoice number
            if 'factuur' in line_lower or 'invoice' in line_lower:
                invoice_match = re.search(r'(?:factuur|invoice)[:\s#]*([\w\-]+)', line, re.IGNORECASE)
                if invoice_match:
                    data['invoice_number'] = invoice_match.group(1)
            
            # Extract total amount - handle "Totaal te betalen € 1.866" format
            if ('totaal' in line_lower and ('betalen' in line_lower or 'te betalen' in line_lower)) or 'total' in line_lower:
                print(f"BTW: Found total line: {line}", flush=True)
                amount_match = re.search(r'€\s*([\d\.\,]+)', line)
                if amount_match:
                    amount_str = amount_match.group(1)
                    print(f"BTW: Extracted amount string: {amount_str}", flush=True)
                    # Handle European number format (1.866 = 1866)
                    if '.' in amount_str and ',' not in amount_str and len(amount_str.split('.')[-1]) == 3:
                        amount_str = amount_str.replace('.', '')
                        print(f"BTW: Converted thousands separator: {amount_str}", flush=True)
                    else:
                        amount_str = amount_str.replace(',', '.')
                    data['total_amount'] = float(amount_str)
                    print(f"BTW: Final amount: {data['total_amount']}", flush=True)
            
            # BTW invoices never have VAT (they ARE the VAT payment)
            # Skip VAT extraction for BTW folder
            
            # Extract date - look for "Afgedrukt op" followed by date
            if 'afgedrukt op' in line_lower:
                print(f"BTW: Found 'Afgedrukt op' line: {line}", flush=True)
                # Check next line for date
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    print(f"BTW: Next line for date: {next_line}", flush=True)
                    date_match = re.search(r'(\d{1,2}-\d{1,2}-\d{4})', next_line)
                    if date_match:
                        date_str = date_match.group(1)
                        print(f"BTW: Found date: {date_str}", flush=True)
                        try:
                            day, month, year = date_str.split('-')
                            data['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                            print(f"BTW: Converted date: {data['date']}", flush=True)
                        except Exception as e:
                            print(f"BTW: Date conversion error: {e}", flush=True)
            
            # Fallback date extraction
            elif 'datum' in line_lower or 'date' in line_lower:
                date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', line)
                if date_match:
                    date_str = date_match.group(1)
                    try:
                        # Handle different date formats
                        if '/' in date_str:
                            day, month, year = date_str.split('/')
                        else:
                            day, month, year = date_str.split('-')
                        
                        if len(year) == 2:
                            year = '20' + year
                        
                        data['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    except:
                        pass
            
            # Extract aangiftenummer
            if 'aangiftenummer' in line_lower:
                aangifte_match = re.search(r'aangiftenummer\s*([\w]+)', line, re.IGNORECASE)
                if aangifte_match:
                    data['aangiftenummer'] = aangifte_match.group(1)
            
            # Extract betalingskenmerk
            if 'betalingskenmerk' in line_lower:
                betaling_match = re.search(r'betalingskenmerk\s*([\d\s]+)', line, re.IGNORECASE)
                if betaling_match:
                    data['betalingskenmerk'] = betaling_match.group(1).strip()
            
            # Extract vendor name (first meaningful line)
            if i < 5 and len(line.strip()) > 3 and not any(x in line_lower for x in ['factuur', 'invoice', 'datum', 'date', 'btw', 'aangiftenummer', 'betalingskenmerk']):
                if not data['vendor_name']:
                    data['vendor_name'] = line.strip()
        
        # Build description with aangiftenummer and betalingskenmerk
        desc_parts = []
        if data['aangiftenummer']:
            desc_parts.append(f"Aangiftenummer {data['aangiftenummer']}")
        if data['betalingskenmerk']:
            desc_parts.append(f"betalingskenmerk {data['betalingskenmerk']}")
        if data['vendor_name']:
            desc_parts.append(data['vendor_name'])
        if data['invoice_number']:
            desc_parts.append(f"Invoice {data['invoice_number']}")
        if data['btw_number']:
            desc_parts.append(f"BTW {data['btw_number']}")
        
        if desc_parts:
            data['description'] = ' '.join(desc_parts)
        
        return data