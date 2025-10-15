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
            
            # Extract invoice number
            if 'factuurnummer' in line_lower or 'invoice number' in line_lower:
                invoice_match = re.search(r'(?:factuurnummer|invoice number)[:\s]*([\\w\\-]+)', line, re.IGNORECASE)
                if invoice_match:
                    data['invoice_number'] = invoice_match.group(1)
            
            # Extract customer number
            if 'klantnummer' in line_lower or 'customer number' in line_lower:
                customer_match = re.search(r'(?:klantnummer|customer number)[:\s]*([\\d\\s/]+)', line, re.IGNORECASE)
                if customer_match:
                    data['customer_number'] = customer_match.group(1).strip()
            
            # Extract VAT amount from "Totaal btw-bedrag" line
            if line.startswith('Totaal btw-bedrag'):
                vat_match = re.search(r'([\\d,\\.]+)', line)
                if vat_match:
                    data['vat_amount'] = float(vat_match.group(1).replace(',', '.'))
            
            # Extract amount from "Totaal te betalen" line
            if line.startswith('Totaal te betalen'):
                amount_match = re.search(r'¤\\s*([\\d,\\.]+)', line)
                if amount_match:
                    data['total_amount'] = float(amount_match.group(1).replace(',', '.'))
            
            # Extract date
            if 'factuurdatum' in line_lower or 'invoice date' in line_lower:
                date_match = re.search(r'(\\d{1,2}[-/]\\d{1,2}[-/]\\d{4})', line)
                if date_match:
                    date_str = date_match.group(1)
                    try:
                        if '/' in date_str:
                            day, month, year = date_str.split('/')
                        else:
                            day, month, year = date_str.split('-')
                        data['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    except:
                        pass
            
        # Build description from full Klantnummer and Factuurnummer lines (first instance only)
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