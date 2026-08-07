# Landingspagina — Gebruikershandleiding

## Overzicht

Met de Landingspagina-functie kun je direct vanuit het myAdmin-platform een publieke website aanmaken voor je bedrijf. Bezoekers kunnen je diensten, accommodaties en bedrijfsinformatie bekijken en contact met je opnemen — zonder dat je een aparte website of CMS nodig hebt.

Je landingspagina is bereikbaar op: `https://[je-domein]/p/[je-slug]`

---

## Aan de slag

### Stap 1: Stel je pagina-slug in

De slug is de URL-vriendelijke naam voor je landingspagina (bijv. `acme-verhuur` wordt `/p/acme-verhuur`).

1. Navigeer naar **Tenant Admin** → **Landingspagina** in de zijbalk
2. Voer je gewenste slug in het **Pagina-slug** veld in
3. Regels: alleen kleine letters, cijfers en koppeltekens (min 3, max 60 tekens)
4. Klik op **Slug opslaan** — het systeem bevestigt beschikbaarheid

> 📷 _[Screenshot: Slug-configuratieveld met "Slug opslaan"-knop]_

---

### Stap 2: Configureer je huisstijl

Stel je bedrijfsidentiteit in zodat deze verschijnt in de footer en social sharing-kaarten.

1. Ga naar het tabblad **Huisstijl**
2. Vul in:
   - **Bedrijfsnaam** en **Tagline**
   - **Logo URL** (upload via Afbeelding uploaden, of gebruik een externe URL)
   - **Primaire kleur** en **Accentkleur** (hex-codes, bijv. `#2D6A4F`)
   - **Contactgegevens**: adres, telefoon, e-mail, KVK, BTW
3. Voeg onder **Social media links** je profiel-URL's toe (Instagram, Facebook, LinkedIn, etc.)
4. Schakel **Deelknoppen tonen** in als je wilt dat bezoekers je pagina makkelijk kunnen delen
5. Klik op **Huisstijl opslaan**

> 📷 _[Screenshot: Huisstijl-instellingen met kleurkiezers en social links]_

---

### Stap 3: Voeg inhoudsblokken toe

Bouw je pagina op door blokken toe te voegen — modulaire inhoudsecties die je in elke volgorde kunt plaatsen.

1. Klik op **+ Blok toevoegen** in de editor-werkbalk
2. Kies een bloktype uit het venster:

| Bloktype         | Beschrijving                                    |
| ---------------- | ----------------------------------------------- |
| Hero             | Grote banner met afbeelding, kop en CTA         |
| Over ons         | Tekstsectie met optionele afbeelding (Markdown) |
| Galerij          | Afbeeldingenraster (upload meerdere foto's)     |
| Testimonials     | Klantervaringen en citaten                      |
| Veelgestelde vr. | Veelgestelde vragen (accordion)                 |
| Prijzen          | Tarieventabel of prijskaarten                   |
| Call to Action   | Prominente CTA-banner met knop                  |
| Insluiten        | Externe content via iframe (alleen HTTPS)       |
| Contact          | Contactformulier voor bezoekersvragen           |
| Accommodaties    | Je STR-accommodaties (live data)                |
| Diensten         | Je ZZP-diensten (live data)                     |

3. Klik na het toevoegen op het blok in de lijst om het **configuratiepaneel** te openen
4. Vul de velden in (titel, inhoud, afbeeldingen, URL's)
5. Kies een **layout-variant** indien beschikbaar (bijv. "Afbeelding rechts", "Gecentreerd")

> 📷 _[Screenshot: Blokkenlijst met sleepgrepen en Blok toevoegen-knop]_

---

### Stap 4: Rangschik je blokken

Herschik blokken met de **↑ / ↓** knoppen op elk blokitem, of sleep ze naar de gewenste volgorde.

- De volgorde in de editor is de volgorde op de gepubliceerde pagina
- Wijzigingen worden automatisch opgeslagen (je ziet "Opgeslagen ✓" in de werkbalk)

---

### Stap 5: Voorbeeld bekijken

Bekijk voor publicatie hoe je pagina eruitziet:

1. Klik op de **Preview**-knop in de werkbalk
2. Het voorbeeld toont je huidige concept precies zoals bezoekers het zullen zien
3. Schakel terug naar **Edit**-modus om wijzigingen aan te brengen

---

### Stap 6: Configureer SEO

Optimaliseer hoe je pagina verschijnt in zoekmachines en social media-shares.

1. Ga naar het tabblad **SEO**
2. Stel je **SEO-titel** in (verschijnt in browsertab en zoekresultaten)
3. Schrijf een **SEO-beschrijving** (getoond onder de titel in Google-resultaten)
4. Upload een **Social share-afbeelding** (aanbevolen 1200×630px) — deze verschijnt wanneer je link wordt gedeeld op Facebook, LinkedIn, WhatsApp
5. Bekijk in de **Deelvoorbeeld**-kaart hoe je link eruitziet
6. Klik op **SEO-instellingen opslaan**

---

### Stap 7: Publiceren

Als je tevreden bent met je pagina:

1. Klik op de groene **Publiceren**-knop
2. Je pagina gaat direct live op de publieke URL
3. Een versie-snapshot wordt opgeslagen (voor toekomstige rollback indien nodig)

Om je pagina offline te halen:

- Klik op **Depubliceren** — de pagina toont een 404 voor bezoekers

---

## Tips & Best Practices

- **Begin met Hero + Over ons** — deze twee blokken geven bezoekers een sterke eerste indruk
- **Voeg een Contact-blok toe** onderaan zodat bezoekers je kunnen bereiken
- **Gebruik afbeeldingen van hoge kwaliteit** — ze worden 1 jaar gecached voor snelle laadtijden
- **Insluiten-blok vereist HTTPS** — alleen `https://`-URL's worden geaccepteerd voor veiligheid
- **Automatisch opslaan**: wijzigingen worden automatisch opgeslagen 2 seconden nadat je stopt met bewerken
- **Moduledata-blokken** (Accommodaties, Diensten): markeer items eerst als "openbaar" in hun respectievelijke beheerpagina's, daarna verschijnen ze op je landingspagina wanneer je publiceert
- **Contactformulier-inzendingen** worden opgeslagen en een notificatie wordt gestuurd naar je geconfigureerde e-mailadres

---

## Problemen oplossen

| Probleem                      | Oplossing                                                 |
| ----------------------------- | --------------------------------------------------------- |
| Pagina toont 404              | Controleer of slug is ingesteld en pagina is gepubliceerd |
| Insluiten-blok toont fout     | Controleer of URL begint met `https://`                   |
| Geen contactnotificaties      | Stel een e-mail in bij Huisstijl → Contactgegevens        |
| Accommodaties/Diensten leeg   | Markeer items als "openbaar" in hun beheersectie          |
| Afbeeldingen verschijnen niet | Controleer of upload slaagde (max 5MB, jpg/png/webp/svg)  |

---

_Laatst bijgewerkt: 2025-01_
