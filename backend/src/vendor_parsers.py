import re
from datetime import datetime
from database import DatabaseManager

class VendorParsers:
    def _parse_date(self, date_str):
        """Convert DD/MM/YYYY to YYYY-MM-DD"""
        try:
            if '/' in date_str:
                day, month, year = date_str.split('/')
            else:
                day, month, year = date_str.split('-')
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except:
            return datetime.now().strftime('%Y-%m-%d')
    
    def _parse_amount(self, amount_str):
        """Convert amount string to float"""
        return float(amount_str.replace(',', '.'))
    
    def _create_basic_data(self, description):
        """Create basic data structure for simple parsers"""
        return {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': description,
            'total_amount': 0.0,
            'vat_amount': 0.0
        }

    def parse_booking(self, lines):
        """Parse Booking.com invoices"""
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
            
            if 'datum:' in line_lower or 'date:' in line_lower:
                date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
                if date_match:
                    data['date'] = self._parse_date(date_match.group(1))
            
            if 'totaal eur' in line_lower or 'total amount due eur' in line_lower:
                amount_match = re.search(r'eur\s+(\d+[,.]\d+)', line_lower)
                if amount_match:
                    data['total_amount'] = self._parse_amount(amount_match.group(1))
            
            if ('vat' in line_lower or 'btw' in line_lower) and 'eur' in line_lower:
                vat_match = re.search(r'eur\s+(\d+[,.]\d+)', line_lower)
                if vat_match:
                    data['vat_amount'] = self._parse_amount(vat_match.group(1))
            
            if 'accommodation number:' in line_lower or 'accommodatie id:' in line_lower:
                accom_match = re.search(r'(\d+)', line)
                if accom_match:
                    data['accommodation_number'] = accom_match.group(1)
            
            if 'invoice number:' in line_lower or 'factuurnummer:' in line_lower:
                invoice_match = re.search(r'(\d+)', line)
                if invoice_match:
                    data['invoice_number'] = invoice_match.group(1)
            
            if 'description:' in line_lower and 'room sales commission' in line_lower:
                data['commission_type'] = 'Room Sales Commission'
        
        if data['vat_amount'] == 0 and data['total_amount'] > 0:
            data['vat_amount'] = round((data['total_amount'] / 121) * 21, 2)
        
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
        data = self._create_basic_data('Avance invoice')
        
        for line in lines:
            amount_match = re.search(r'€?\s*(\d+[,.]?\d*)', line)
            if amount_match and data['total_amount'] == 0:
                data['total_amount'] = self._parse_amount(amount_match.group(1))
        
        return data
    
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
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            if 'receipt no.' in line_lower:
                receipt_match = re.search(r'receipt no\.\s*([A-Z0-9\-]+)', line, re.IGNORECASE)
                if receipt_match:
                    data['receipt_number'] = receipt_match.group(1)
            
            if ('date' in line_lower and 'description' in line_lower and 
                ('service' in line_lower or 'period' in line_lower)):
                if i + 1 < len(lines):
                    data_line = lines[i + 1]
                    
                    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', data_line)
                    if date_match:
                        data['date'] = self._parse_date(date_match.group(1))
                    
                    amounts = re.findall(r'€([\d,\.]+)', data_line)
                    if len(amounts) >= 3:
                        try:
                            data['vat_amount'] = self._parse_amount(amounts[1])
                            data['total_amount'] = self._parse_amount(amounts[2])
                        except:
                            pass
                    
                    period_match = re.search(r'(\d{2}/\d{2}/\d{4}–\d{2}/\d{2}/\d{4})', data_line)
                    if period_match:
                        data['subscription_period'] = period_match.group(1)
                    
                    break
        
        desc_parts = ["Netflix Streaming Service"]
        if data['subscription_period']:
            desc_parts.append(data['subscription_period'])
        if data['receipt_number']:
            desc_parts.append(f"Receipt No. {data['receipt_number']}")
        
        data['description'] = ' '.join(desc_parts)
        return data
    
    def parse_ziggo(self, lines):
        """Parse Ziggo VT invoices"""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'Ziggo VT service',
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'invoice_number': '',
            'customer_number': ''
        }
        
        for line in lines:
            line_lower = line.lower()
            
            if 'factuurnummer' in line_lower or 'invoice number' in line_lower:
                invoice_match = re.search(r'(?:factuurnummer|invoice number)[:\s]*([\\w\\-]+)', line, re.IGNORECASE)
                if invoice_match:
                    data['invoice_number'] = invoice_match.group(1)
            
            if 'klantnummer:' in line_lower:
                customer_match = re.search(r'klantnummer:\s*([\d\s/]+)', line, re.IGNORECASE)
                if customer_match:
                    data['customer_number'] = customer_match.group(1).strip()
            
            if 'totaal' in line_lower:
                amounts = re.findall(r'€\s*([\d,\.]+)', line)
                if len(amounts) == 3:
                    data['vat_amount'] = self._parse_amount(amounts[1])
                    data['total_amount'] = self._parse_amount(amounts[2])
                elif len(amounts) == 1:
                    data['total_amount'] = self._parse_amount(amounts[0])
            
            if 'factuurdatum' in line_lower or 'invoice date' in line_lower:
                date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})', line)
                if date_match:
                    data['date'] = self._parse_date(date_match.group(1))
            
            if line.startswith('Abonnementskosten'):
                data['description'] = line.strip()
        
        return data
    
    def parse_vodafone(self, lines):
        """Parse Vodafone invoices"""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'Vodafone service',
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'invoice_number': '',
            'customer_number': ''
        }
        
        for line in lines:
            line_lower = line.lower()
            
            if 'factuurnummer' in line_lower or 'invoice number' in line_lower:
                invoice_match = re.search(r'(?:factuurnummer|invoice number)[:\s]*([\\w\\-]+)', line, re.IGNORECASE)
                if invoice_match:
                    data['invoice_number'] = invoice_match.group(1)
            
            if 'klantnummer' in line_lower or 'customer number' in line_lower:
                customer_match = re.search(r'(?:klantnummer|customer number)[:\s]*([\d\s/]+)', line, re.IGNORECASE)
                if customer_match:
                    data['customer_number'] = customer_match.group(1).strip()
            
            if line.startswith('Totaal btw-bedrag'):
                vat_match = re.search(r'([\d,\.]+)', line)
                if vat_match:
                    data['vat_amount'] = self._parse_amount(vat_match.group(1))
            
            if line.startswith('Totaal te betalen'):
                amount_match = re.search(r'¤\s*([\d,\.]+)', line)
                if amount_match:
                    data['total_amount'] = self._parse_amount(amount_match.group(1))
            
            if 'factuurdatum' in line_lower or 'invoice date' in line_lower:
                date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})', line)
                if date_match:
                    data['date'] = self._parse_date(date_match.group(1))
        
        desc_parts = []
        factuurnummer_found = False
        for line in lines:
            if line.startswith('Klantnummer'):
                desc_parts.append(line.strip())
            elif line.startswith('Factuurnummer') and not factuurnummer_found:
                desc_parts.append(line.strip())
                factuurnummer_found = True
        
        if desc_parts:
            data['description'] = ' '.join(desc_parts)
        
        return data
    
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
            
            if 'vat (eur):' in line_lower:
                vat_match = re.search(r'vat \(eur\):\s*([\d,\.]+)', line_lower)
                if vat_match:
                    data['vat_amount'] = self._parse_amount(vat_match.group(1))
            
            if 'total (eur):' in line_lower:
                total_match = re.search(r'total \(eur\):\s*([\d,\.]+)', line_lower)
                if total_match:
                    data['total_amount'] = self._parse_amount(total_match.group(1))
            
            if 'order number:' in line_lower:
                order_match = re.search(r'order number:\s*(\d+)', line_lower)
                if order_match:
                    data['order_number'] = order_match.group(1)
            
            if 'product details' in line_lower and 'price' in line_lower and 'qty' in line_lower:
                if i + 1 < len(lines):
                    data['product_details'] = lines[i + 1].strip()
            
            if 'mountain view' in line_lower and 'ca 94041 usa' in line_lower:
                if i + 1 < len(lines):
                    date_line = lines[i + 1].strip()
                    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', date_line)
                    if date_match:
                        month, day, year = date_match.group(1).split('/')
                        data['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
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
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'BTW invoice',
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'btw_number': '',
            'invoice_number': '',
            'vendor_name': '',
            'aangiftenummer': '',
            'betalingskenmerk': ''
        }
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            if 'btw' in line_lower and re.search(r'[a-z]{2}\d{9}b\d{2}', line_lower):
                btw_match = re.search(r'([a-z]{2}\d{9}b\d{2})', line_lower)
                if btw_match:
                    data['btw_number'] = btw_match.group(1).upper()
            
            if 'factuur' in line_lower or 'invoice' in line_lower:
                invoice_match = re.search(r'(?:factuur|invoice)[:\s#]*([\\w\\-]+)', line, re.IGNORECASE)
                if invoice_match:
                    data['invoice_number'] = invoice_match.group(1)
            
            if ('totaal' in line_lower and ('betalen' in line_lower or 'te betalen' in line_lower)) or 'total' in line_lower:
                amount_match = re.search(r'€\s*([\d\.\,]+)', line)
                if amount_match:
                    amount_str = amount_match.group(1)
                    if '.' in amount_str and ',' not in amount_str and len(amount_str.split('.')[-1]) == 3:
                        amount_str = amount_str.replace('.', '')
                    else:
                        amount_str = amount_str.replace(',', '.')
                    data['total_amount'] = float(amount_str)
            
            if 'afgedrukt op' in line_lower:
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    date_match = re.search(r'(\d{1,2}-\d{1,2}-\d{4})', next_line)
                    if date_match:
                        data['date'] = self._parse_date(date_match.group(1))
            
            elif 'datum' in line_lower or 'date' in line_lower:
                date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', line)
                if date_match:
                    data['date'] = self._parse_date(date_match.group(1))
            
            if 'aangiftenummer' in line_lower:
                aangifte_match = re.search(r'aangiftenummer\s*([\\w]+)', line, re.IGNORECASE)
                if aangifte_match:
                    data['aangiftenummer'] = aangifte_match.group(1)
            
            if 'betalingskenmerk' in line_lower:
                betaling_match = re.search(r'betalingskenmerk\s*([\d\s]+)', line, re.IGNORECASE)
                if betaling_match:
                    data['betalingskenmerk'] = betaling_match.group(1).strip()
            
            if i < 5 and len(line.strip()) > 3 and not any(x in line_lower for x in ['factuur', 'invoice', 'datum', 'date', 'btw', 'aangiftenummer', 'betalingskenmerk']):
                if not data['vendor_name']:
                    data['vendor_name'] = line.strip()
        
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

    # Simple parsers for vendors without complex logic
    def parse_action(self, lines):
        return self._create_basic_data('Action invoice')
    
    def parse_mastercard(self, lines):
        return self._create_basic_data('Mastercard transaction')
    
    def parse_visa(self, lines):
        return self._create_basic_data('Visa transaction')
    
    def parse_bolcom(self, lines):
        """Parse Bol.com invoices - extract factuurnummer and klantnummer from specific lines"""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'Bol.com order',
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'factuurnummer': '',
            'klantnummer': ''
        }
        
        # Look for factuurnummer and klantnummer in specific line positions
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Extract date from "Aankoopdatum" line
            if 'aankoopdatum' in line_lower:
                parts = line.split()
                if len(parts) >= 6:
                    try:
                        day = parts[5] if len(parts) > 5 else parts[-1]
                        month = parts[4] if len(parts) > 4 else parts[-2]
                        year = parts[3] if len(parts) > 3 else parts[-3]
                        
                        month_names = {
                            'januari': '01', 'februari': '02', 'maart': '03', 'april': '04',
                            'mei': '05', 'juni': '06', 'juli': '07', 'augustus': '08',
                            'september': '09', 'oktober': '10', 'november': '11', 'december': '12'
                        }
                        if month.lower() in month_names:
                            month = month_names[month.lower()]
                        elif month.isdigit():
                            month = month.zfill(2)
                        
                        data['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    except:
                        pass
            
            # Extract amounts from "Totaalbedrag" line
            if 'totaalbedrag' in line_lower:
                amounts = re.findall(r'([\d,\.]+)', line)
                if len(amounts) >= 3:
                    data['total_amount'] = self._parse_amount(amounts[0])
                    data['vat_amount'] = self._parse_amount(amounts[2])
                elif len(amounts) >= 1:
                    data['total_amount'] = self._parse_amount(amounts[0])
            
            # Extract VAT from "21% BTW €" line
            if '21% btw €' in line_lower:
                btw_parts = line.split('BTW')
                if len(btw_parts) > 1:
                    vat_match = re.search(r'([\d,\.]+)', btw_parts[1])
                    if vat_match:
                        data['vat_amount'] = self._parse_amount(vat_match.group(1))
        
        # Extract factuurnummer and klantnummer from lines 14 and 11 (0-indexed: 13 and 10)
        if 'factuurnummer' in line_lower:
            # Line 14 should contain factuurnummer
            line_lower = line_lower.strip()
            factuurnummer_match = re.search(r'(\d+)', line_lower)
            if factuurnummer_match:
                data['factuurnummer'] = factuurnummer_match.group(1)
        
        if 'klantnemmuer' in line_lower:
            # Line 11 should contain klantnummer
            line_lower = line_lower.strip()
            klantnummer_match = re.search(r'(\d+)', line_lower)
            if klantnummer_match:
                data['klantnummer'] = klantnummer_match.group(1)
        
        # Build description in the expected format: "Factuurnummer [number] Klantnummer [number]"
        desc_parts = []
        if data['factuurnummer']:
            desc_parts.append(f"Factuurnummer {data['factuurnummer']}")
        if data['klantnummer']:
            desc_parts.append(f"Klantnummer {data['klantnummer']}")
        
        if desc_parts:
            data['description'] = ' '.join(desc_parts)
        
        return data
    
    def parse_picnic(self, lines):
        return self._create_basic_data('Picnic order')
    
    def parse_temu(self, lines):
        return self._create_basic_data('Temu order')
    
    def parse_kuwait(self, lines):
        """Parse kuwait petroleum fuel invoices"""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'Kuwait Petroleum fuel invoice',
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'invoice_number': '',
            'station_number': '9429002351'
        }
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Extract date from "^ Datum :" line
            if line.strip().startswith('Datum :'):
                date_part = line.split('9429002351')[0] if '9429002351' in line else line
                date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})', date_part)
                if date_match:
                    data['date'] = self._parse_date(date_match.group(1))
            
            # Extract amounts from "TOTAAL FACTUUR :" line
            if 'TOTAAL FACTUUR :' in line:
                amounts_part = line.split(' : ')[1] if ' : ' in line else line
                amounts = re.findall(r'([\d,\.]+)', amounts_part)
                if len(amounts) >= 2:
                    try:
                        # Based on R script: amounts[3] is VAT, amounts[4] is total
                        if len(amounts) >= 4:
                            data['vat_amount'] = self._parse_amount(amounts[2])  # Third amount (index 2)
                            data['total_amount'] = self._parse_amount(amounts[3])  # Fourth amount (index 3)
                        elif len(amounts) >= 2:
                            data['vat_amount'] = self._parse_amount(amounts[0])
                            data['total_amount'] = self._parse_amount(amounts[1])
                    except:
                        pass
            
            # Extract invoice number from "FACTUUR NR :" line
            if 'FACTUUR NR :' in line:
                invoice_match = re.search(r'FACTUUR NR :\s*([\w\-]+)', line)
                if invoice_match:
                    data['invoice_number'] = invoice_match.group(1)
        
        # Build description: concatenate FACTUUR NR and TOTAAL FACTUUR lines
        factuur_nr_line = ''
        totaal_factuur_line = ''
        
        for line in lines:
            if 'FACTUUR NR :' in line:
                factuur_nr_line = line.strip()
            elif 'TOTAAL FACTUUR :' in line:
                # Extract only the part starting from TOTAAL FACTUUR
                totaal_part = line[line.find('TOTAAL FACTUUR'):].strip()
                totaal_factuur_line = totaal_part
        
        if factuur_nr_line and totaal_factuur_line:
            # Concatenate and remove double spaces
            description = f"{factuur_nr_line}; {totaal_factuur_line}"
            data['description'] = re.sub(r'\s+', ' ', description)
        
        return data