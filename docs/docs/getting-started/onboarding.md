# Modules instellen

> Stap-voor-stap handleiding om elke module in gebruik te nemen.

## Overzicht

myAdmin bestaat uit meerdere modules die je afzonderlijk kunt activeren. Hieronder vind je per module wat je nodig hebt en welke eerste stappen je moet nemen om aan de slag te gaan.

!!! info
Modules worden ingeschakeld door je SysAdmin. Als je een module niet ziet, vraag dan of deze voor je tenant is geactiveerd.

---

## Bankzaken

Importeer bankafschriften, stel patronen in voor automatische rekeningtoewijzing en verwerk transacties.

**Vereisten:**

- FIN-module moet actief zijn
- CSV-bankafschriften van je bank (Rabobank, Revolut of creditcard)

**Eerste stappen:**

1. Download een bankafschrift als CSV vanuit je internetbankieren
2. Ga naar **Bankzaken** en klik op **Importeren**
3. Upload het CSV-bestand en bekijk de geïmporteerde transacties
4. Klik op **Patronen toepassen** om automatisch rekeningen toe te wijzen
5. Controleer de transacties en sla ze op

→ Meer: [Bankzaken](../banking/index.md)

---

## Facturen

Upload PDF-facturen, laat AI de gegevens uitlezen en sla alles op in Google Drive.

**Vereisten:**

- FIN-module moet actief zijn
- Google Drive moet geconfigureerd zijn (vraag je Tenant Admin)

**Eerste stappen:**

1. Controleer of Google Drive is ingesteld via **Instellingen**
2. Ga naar **Facturen** en klik op **Uploaden**
3. Selecteer een PDF-factuur
4. Wacht tot de AI de gegevens heeft uitgelezen
5. Controleer het resultaat en klik op **Goedkeuren**

→ Meer: [Facturen](../invoices/index.md)

---

## STR (Kortetermijnverhuur)

Verwerk omzetbestanden van Airbnb, Booking.com en andere verhuurplatforms.

**Vereisten:**

- FIN-module moet actief zijn
- Omzetbestanden van je verhuurplatform (CSV of Excel)

**Eerste stappen:**

1. Download een omzetbestand van Airbnb of Booking.com
2. Ga naar **STR** en klik op **Importeren**
3. Selecteer het platform en upload het bestand
4. Bekijk de gerealiseerde en geplande boekingen
5. Controleer de berekende bedragen en sla op

→ Meer: [STR](../str/index.md)

---

## STR Prijzen

Bekijk AI-gestuurde prijsaanbevelingen voor je verhuurobjecten.

**Vereisten:**

- STR-module moet actief zijn
- Minimaal één seizoen aan boekingsdata geïmporteerd

**Eerste stappen:**

1. Zorg dat je voldoende boekingsdata hebt geïmporteerd via de STR-module
2. Ga naar **STR Prijzen**
3. Bekijk de prijsaanbevelingen per object en periode
4. Vergelijk de aanbevolen prijzen met je huidige tarieven
5. Pas suggesties toe waar gewenst

→ Meer: [STR Prijzen](../str-pricing/index.md)

---

## ZZP Facturatie

Maak en verstuur facturen aan je klanten, registreer uren per project en beheer je debiteuren en crediteuren.

**Vereisten:**

- FIN-module moet actief zijn
- ZZP-module moet zijn ingeschakeld door je SysAdmin

**Eerste stappen:**

1. **Controleer of de FIN-module actief is** — de ZZP-module vereist FIN
2. **Maak je eerste contact aan** — ga naar **ZZP** → **Contacten** en maak een contact aan met een uniek Klant-ID en bedrijfsnaam
3. **Maak je eerste product of dienst aan** — ga naar **ZZP** → **Producten** en maak een product aan met prijs en BTW-code
4. **Maak je eerste factuur aan** — ga naar **ZZP** → **Facturen**, selecteer het contact, voeg regelitems toe en sla op als concept
5. **Verstuur de factuur** — open het concept en klik op **Versturen** om de PDF te genereren, te boeken in FIN en per e-mail te versturen
6. **Stel urenregistratie in** (optioneel) — als je uren wilt bijhouden, ga naar **ZZP** → **Urenregistratie** en registreer je eerste uren
7. **Configureer e-mailinstellingen** (optioneel) — vraag je Tenant Admin om het e-mail onderwerp en de afzender in te stellen

!!! tip
Begin met één contact en één product om het proces te leren kennen. Je kunt later altijd meer toevoegen.

→ Meer: [ZZP Facturatie](../zzp/index.md)

---

## Rapportages

Bekijk interactieve dashboards, genereer winst- en verliesrekeningen en exporteer naar Excel.

**Vereisten:**

- FIN-module moet actief zijn
- Transacties moeten zijn geïmporteerd en verwerkt

**Eerste stappen:**

1. Zorg dat je bankafschriften en/of facturen hebt verwerkt
2. Ga naar **Rapportages**
3. Kies een dashboard of rapport
4. Stel de gewenste periode in
5. Exporteer naar Excel indien nodig

→ Meer: [Rapportages](../reports/index.md)

---

## Belastingen

Bereid BTW-aangiften, inkomstenbelasting (IB) en toeristenbelasting voor.

**Vereisten:**

- FIN-module moet actief zijn
- Transacties moeten zijn verwerkt voor de betreffende periode

**Eerste stappen:**

1. Zorg dat alle transacties voor de aangifteperiode zijn verwerkt
2. Ga naar **Belastingen** en kies het type aangifte (BTW, IB of toeristenbelasting)
3. Selecteer de periode
4. Controleer de berekende bedragen
5. Exporteer het overzicht voor je aangifte

→ Meer: [Belastingen](../tax/index.md)

---

## PDF Validatie

Controleer of Google Drive-links in je transacties nog werken en repareer verbroken koppelingen.

**Vereisten:**

- Google Drive moet geconfigureerd zijn
- Transacties met Google Drive-links in je administratie

**Eerste stappen:**

1. Ga naar **PDF Validatie**
2. Klik op **Validatie starten**
3. Wacht tot de controle is afgerond
4. Bekijk de resultaten — groene links werken, rode links zijn verbroken
5. Repareer verbroken links waar nodig

→ Meer: [PDF Validatie](../pdf-validation/index.md)
