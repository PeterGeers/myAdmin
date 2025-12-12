from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
from datetime import datetime
import os

class InvoiceGenerator:
    def __init__(self):
        self.logo_cache = {}
        
    def download_logo(self, company_name):
        """Download company logo from Google Images"""
        if company_name in self.logo_cache:
            return self.logo_cache[company_name]
        
        # Simple logo URLs for common Dutch stores
        logos = {
            'Intratuin': 'https://www.intratuin.nl/static/version1732527600/frontend/Intratuin/default/nl_NL/images/logo.svg',
            'Action': 'https://www.action.com/globalassets/cmsassets/action-logo.png',
            'Jumbo': 'https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Jumbo_Logo.svg/320px-Jumbo_Logo.svg.png',
            'Hornbach': 'https://upload.wikimedia.org/wikipedia/commons/thumb/4/4f/Hornbach_Logo.svg/320px-Hornbach_Logo.svg.png',
            'Karwei': 'https://upload.wikimedia.org/wikipedia/commons/thumb/9/9f/Karwei_logo.svg/320px-Karwei_logo.svg.png'
        }
        
        try:
            if company_name in logos:
                response = requests.get(logos[company_name], timeout=5)
                logo = Image.open(BytesIO(response.content))
                self.logo_cache[company_name] = logo
                return logo
        except:
            pass
        
        return None
    
    def generate_receipt(self, company_name, filename, total_amount, vat_amount, date=None):
        """Generate a simple receipt image"""
        # Create image
        width, height = 600, 800
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Try to use a font, fallback to default
        try:
            title_font = ImageFont.truetype("arial.ttf", 40)
            normal_font = ImageFont.truetype("arial.ttf", 24)
            small_font = ImageFont.truetype("arial.ttf", 18)
        except:
            title_font = ImageFont.load_default()
            normal_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        y_pos = 50
        
        # Download and add logo
        logo = self.download_logo(company_name)
        if logo:
            logo.thumbnail((200, 100))
            img.paste(logo, (width//2 - logo.width//2, y_pos))
            y_pos += logo.height + 30
        else:
            # Draw company name if no logo
            draw.text((width//2, y_pos), company_name, fill='black', font=title_font, anchor='mt')
            y_pos += 60
        
        # Date
        if not date:
            date = datetime.now().strftime('%d-%m-%Y')
        draw.text((width//2, y_pos), f"Datum: {date}", fill='black', font=normal_font, anchor='mt')
        y_pos += 80
        
        # Separator line
        draw.line([(50, y_pos), (width-50, y_pos)], fill='black', width=2)
        y_pos += 40
        
        # Receipt title
        draw.text((width//2, y_pos), "KASSABON", fill='black', font=title_font, anchor='mt')
        y_pos += 80
        
        # Calculate amounts
        net_amount = total_amount - vat_amount
        
        # Amounts
        draw.text((100, y_pos), "Subtotaal:", fill='black', font=normal_font)
        draw.text((width-100, y_pos), f"€ {net_amount:.2f}", fill='black', font=normal_font, anchor='rt')
        y_pos += 50
        
        draw.text((100, y_pos), "BTW:", fill='black', font=normal_font)
        draw.text((width-100, y_pos), f"€ {vat_amount:.2f}", fill='black', font=normal_font, anchor='rt')
        y_pos += 50
        
        # Separator line
        draw.line([(50, y_pos), (width-50, y_pos)], fill='black', width=2)
        y_pos += 40
        
        # Total
        draw.text((100, y_pos), "TOTAAL:", fill='black', font=title_font)
        draw.text((width-100, y_pos), f"€ {total_amount:.2f}", fill='black', font=title_font, anchor='rt')
        y_pos += 100
        
        # Footer
        draw.text((width//2, height-50), "Gegenereerde kassabon", fill='gray', font=small_font, anchor='mt')
        
        return img
    
    def save_receipt(self, img, output_path):
        """Save receipt image"""
        img.save(output_path, 'JPEG', quality=95)
        return output_path

# Example usage
if __name__ == '__main__':
    generator = InvoiceGenerator()
    
    # Generate Intratuin receipt
    receipt = generator.generate_receipt(
        company_name='Intratuin',
        filename='Intratuin 202502.jpg',
        total_amount=193.29,
        vat_amount=33.55,
        date='13-05-2025'
    )
    
    output_path = 'generated_receipts/Intratuin_202502.jpg'
    os.makedirs('generated_receipts', exist_ok=True)
    generator.save_receipt(receipt, output_path)
    print(f"Receipt saved to: {output_path}")
