# 📊 myReporting: React + MySQL + Google Charts Reporting Dashboard

## ✅ Doel
Een veilige, interactieve rapportagefunctie bouwen in ReactJS die financiële data uit een MySQL-database ophaalt en visualiseert met Google Charts.

## 🧱 Architectuur

| Component     | Technologie         | Functie                                 |
|---------------|---------------------|------------------------------------------|
| Frontend      | ReactJS + Google Charts | UI en interactieve visualisaties        |
| Backend API   | Node.js + Express   | Data ophalen en filteren via REST API   |
| Database      | MySQL               | Opslag van financiële gegevens          |
| Authenticatie | JWT + Google OAuth  | Beveiligde toegang en rolbeheer         |

## 🔧 Functionaliteiten

### 1. 📈 Data Visualisatie
- Tabellen, lijngrafieken, cirkeldiagrammen via `react-google-charts`
- Dynamische updates op basis van filters

### 2. 🔍 Filters
- Filteren op datum, categorie of andere parameters
- Query parameters worden naar backend gestuurd

### 3. 📤 Exportopties
- **CSV**: Data downloaden als spreadsheet
- **PDF**: Charts exporteren als afbeelding in PDF

### 4. 🔐 Authenticatie
- JWT login met gebruikersrollen (admin, analyst, viewer)
- Google OAuth login met automatische gebruikersaanmaak

## 👥 Gebruikersrollen
| Rol     | Rechten                        |
|---------|--------------------------------|
| Admin   | Alles: bekijken, exporteren, beheren |
| Analyst | Bekijken en exporteren         |
| Viewer  | Alleen bekijken                |


## 🛠 Aanbevelingen
- Gebruik `.env` voor gevoelige gegevens
- Voeg paginering of caching toe bij grote datasets
- Gebruik HTTPS en beveiligde cookies in productie
- Voeg audit logs of e-mailrapportages toe indien nodig
