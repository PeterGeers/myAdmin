# STR Invoice Generator

Genereer professionele facturen voor Short Term Rental boekingen op basis van data uit de BNB database.

## Functionaliteit

### ✨ Hoofdfuncties
- **Boeking zoeken**: Zoek boekingen op gastnaam of reserveringscode met regex matching
- **Factuur genereren**: Maak HTML facturen in Nederlands of Engels
- **Template systeem**: Gebruik professionele HTML templates opgeslagen in Google Drive
- **Print functie**: Direct printen vanuit de browser
- **Automatische berekeningen**: Prijs per nacht, toeristenbelasting, totalen

### 🔍 Zoekfunctionaliteit
```sql
-- Zoekt in bnb tabel op:
WHERE guestName LIKE %query% OR reservationCode LIKE %query%
```

### 📊 Data Extractie
Haalt de volgende velden op uit de `bnb` tabel:
- `amountGross` - Totaalbedrag
- `checkinDate` - Incheckdatum  
- `guestName` - Gastnaam
- `channel` - Boekingskanaal (Airbnb, Booking.com)
- `listing` - Accommodatie naam
- `nights` - Aantal nachten
- `guests` - Aantal gasten
- `reservationCode` - Reserveringscode
- `amountTouristTax` - Toeristenbelasting

### 🧮 Automatische Berekeningen
- **Prijs per nacht**: `amountGross / nights`
- **Subtotaal**: `amountGross - toeristenbelasting`
- **Toeristenbelasting per persoon**: `amountTouristTax / guests`
- **Datumformaten**: Automatische conversie naar DD-MM-YYYY

## Templates

### 📁 Template Locaties
- **Lokaal**: `backend/templates/`
- **Google Drive**: [Templates Folder](https://drive.google.com/drive/folders/12FJAYbX5MI3wpGxwahcHykRQfUCRZob1)

### 🌐 Beschikbare Templates
1. **str_invoice_nl.html** - Nederlandse factuur
2. **str_invoice_en.html** - Engelse factuur

### 🎨 Template Features
- Responsive HTML/CSS design
- Logo integratie (Google Drive link)
- Professionele styling met bedrijfsgegevens
- Conditionele secties (toeristenbelasting, schoonmaakkosten)
- Print-geoptimaliseerd

## API Endpoints

### 🔍 Zoeken
```http
GET /api/str-invoice/search-booking?query={gastnaam_of_code}
```

### 📄 Factuur Genereren
```http
POST /api/str-invoice/generate-invoice
Content-Type: application/json

{
  "reservationCode": "ABC123",
  "language": "nl"  // "nl" of "en"
}
```

### ⬆️ Templates Uploaden
```http
POST /api/str-invoice/upload-template
```

## Installatie & Setup

### 1. Backend Dependencies
```bash
# Geen extra dependencies nodig - gebruikt bestaande Flask setup
```

### 2. Templates Uploaden
```bash
cd backend
python upload_templates.py
```

### 3. Frontend Component
De `STRInvoice` component is toegevoegd aan de hoofdnavigatie.

### 4. Testen
```bash
cd backend
python test_str_invoice.py
```

## Gebruik

### 🖥️ Frontend Interface
1. Ga naar **STR Invoice Generator** in het hoofdmenu
2. Voer gastnaam of reserveringscode in
3. Selecteer taal (Nederlands/Engels)
4. Klik **Search** om boekingen te vinden
5. Klik **Generate Invoice** bij gewenste boeking
6. Preview en print de factuur

### 🔧 Backend Integration
```python
from str_invoice_routes import str_invoice_bp
app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')
```

## Template Customization

### 🏢 Bedrijfsgegevens Aanpassen
Bewerk de templates om bedrijfsgegevens te wijzigen:
```html
<div class="company-info">
    <strong>Uw Bedrijfsnaam</strong><br>
    Adres<br>
    Postcode Plaats<br>
    Nederland<br>
    BTW: NL123456789B01<br>
    KvK: 12345678
</div>
```

### 🎨 Styling Aanpassen
Wijzig CSS in de `<style>` sectie van de templates voor:
- Kleuren en fonts
- Logo grootte en positie
- Tabel styling
- Print layout

### 🖼️ Logo Wijzigen
Update de logo URL in beide templates:
```html
<img src="https://drive.google.com/uc?id=1vNPUwHWkUdCWC01VG_VgQHt8PYLdg8YL" alt="Logo" class="logo">
```

## Troubleshooting

### ❌ Geen boekingen gevonden
- Controleer of de BNB data correct is geïmporteerd
- Verificeer de zoekterm (gastnaam of reserveringscode)
- Check database connectie

### 🖨️ Print problemen
- Gebruik Chrome/Edge voor beste print resultaten
- Check CSS print media queries
- Controleer browser print instellingen

### 📁 Template niet gevonden
```bash
# Upload templates opnieuw
python upload_templates.py
```

### 🔗 Google Drive toegang
- Controleer `credentials.json` en `token.json`
- Verificeer folder permissions
- Test Google Drive API connectie

## Toekomstige Uitbreidingen

### 📧 Email Integratie
- Automatisch versturen van facturen
- Gmail API integratie

### 💾 PDF Export
- Server-side PDF generatie
- Automatische opslag in Google Drive

### 🧾 Factuur Nummering
- Sequentiële factuurnnummers
- Database tracking van verzonden facturen

### 📊 Rapportage
- Factuur overzichten
- Revenue tracking per periode

## Support

Voor vragen of problemen:
1. Check de logs in de browser console
2. Controleer backend logs voor API errors
3. Test database connectie met BNB data
4. Verificeer Google Drive permissions