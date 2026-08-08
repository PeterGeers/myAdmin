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

## Je eigen domein koppelen

Je kunt je landingspagina bereikbaar maken op je eigen domeinnaam, zoals `www.jouwbedrijf.nl`. Dit zorgt voor een professionele uitstraling en is goed voor vindbaarheid.

### Wat heb je nodig?

- Een gepubliceerde landingspagina (met slug)
- Toegang tot de DNS-instellingen bij je domeinprovider (bijv. TransIP, Hostnet, Cloudflare)

### Optie A: Een subdomein koppelen (bijv. www.jouwbedrijf.nl)

Dit is de eenvoudigste optie en werkt bij **alle** DNS-providers.

1. Ga naar **Tenant Admin** → **Landingspagina** → **Domeinen**
2. Voer je domein in bij **Eigen domein**, bijv. `www.jouwbedrijf.nl`
3. Klik op **Domein registreren**
4. Het systeem toont de DNS-instellingen die je moet invoeren:

| Type  | Naam | Waarde                            |
| ----- | ---- | --------------------------------- |
| CNAME | www  | _(waarde getoond in het systeem)_ |

5. Log in bij je domeinprovider en ga naar DNS-beheer
6. Voeg een **CNAME-record** toe met de getoonde waarden
7. Wacht 5–30 minuten tot de DNS-wijziging is doorgevoerd
8. Ga terug naar myAdmin en klik op **Verifiëren**
9. Als de verificatie slaagt, is je pagina live op `www.jouwbedrijf.nl`

### Optie B: Een hoofddomein koppelen (bijv. jouwbedrijf.nl — zonder www)

Hoofddomeinen (ook wel "root domain" of "apex domain" genoemd) kunnen **geen** gewoon CNAME-record gebruiken. Je hebt een speciaal ALIAS- of ANAME-record nodig.

**Providers die ALIAS/ANAME ondersteunen:**

- Route 53 (AWS)
- Cloudflare
- DNSimple
- NS1
- Constellix

Als je provider ALIAS ondersteunt:

1. Ga naar **Tenant Admin** → **Landingspagina** → **Domeinen**
2. Voer je hoofddomein in, bijv. `jouwbedrijf.nl`
3. Klik op **Domein registreren**
4. Het systeem toont de benodigde DNS-instellingen
5. Maak bij je provider een **ALIAS-record** (of ANAME) aan op `@` met de getoonde waarde
6. Wacht op DNS-propagatie en klik op **Verifiëren**

**Providers ZONDER ALIAS-ondersteuning:**

- TransIP (basispakket)
- Hostnet
- Antagonist

### Alternatief: Redirect van hoofddomein naar www

Als je provider geen ALIAS ondersteunt, gebruik dan deze werkwijze:

1. Koppel eerst `www.jouwbedrijf.nl` via een CNAME (Optie A hierboven)
2. Stel bij je provider een **301-redirect** in van `jouwbedrijf.nl` → `www.jouwbedrijf.nl`
   - Bij de meeste providers vind je dit onder "Doorsturen" of "Redirects"
3. Bezoekers die `jouwbedrijf.nl` bezoeken worden automatisch doorgestuurd naar `www.jouwbedrijf.nl`

> 💡 _Tip: de combinatie van CNAME op www + redirect van het hoofddomein is de meest betrouwbare aanpak als je provider geen ALIAS ondersteunt._

---

## Het jabaki.nl subdomein gebruiken

Elke tenant krijgt gratis een subdomein op `jabaki.nl`. Dit is handig als je (nog) geen eigen domeinnaam hebt, of om snel een link te delen.

### Hoe schakel je het in?

1. Ga naar **Tenant Admin** → **Landingspagina** → **Domeinen**
2. Je ziet het Jabaki-subdomein: `jouw-slug.jabaki.nl`
3. Klik op de schakelaar om het subdomein te **activeren**
4. Je pagina is direct bereikbaar op `https://jouw-slug.jabaki.nl`

### Preview-URL

Zodra geactiveerd, verschijnt er een klikbare link naar je subdomein. Je kunt deze direct kopiëren en delen met klanten of op social media.

### Wanneer is het handig?

- Je hebt (nog) geen eigen domeinnaam
- Je wilt snel een professionele link delen
- Je wilt je pagina testen voordat je een eigen domein koppelt
- Als tijdelijke oplossing terwijl je wacht op DNS-propagatie van je eigen domein

> 💡 _Tip: als je later een eigen domein koppelt, blijft het jabaki-subdomein ook gewoon werken. Bezoekers kunnen beide URL's gebruiken._

---

## Probleemoplossing — Domeinen

| Probleem                                  | Oorzaak & Oplossing                                                                                                                                                                                                       |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Mijn domein toont een certificaatfout** | Je DNS-records zijn waarschijnlijk nog niet doorgevoerd, of het CNAME-record wijst naar de verkeerde waarde. Controleer bij je provider of het record correct is ingesteld. Wacht maximaal 30 minuten en probeer opnieuw. |
| **Mijn pagina laadt niet op mijn domein** | De verificatie is mogelijk nog niet afgerond. Ga naar Domeinen in myAdmin en klik op **Verifiëren**. Zorg dat het DNS-record correct is ingesteld.                                                                        |
| **Hoe lang duurt de verificatie?**        | Na het instellen van je DNS-record duurt het meestal 5–30 minuten. In zeldzame gevallen kan het tot 24 uur duren bij trage providers.                                                                                     |
| **Mijn jabaki-subdomein werkt niet**      | Controleer of je subdomein is geactiveerd in het Domeinen-paneel. Je pagina moet ook gepubliceerd zijn.                                                                                                                   |
| **Ik wil mijn domein wijzigen**           | Verwijder eerst het huidige domein via het Domeinen-paneel, en registreer daarna het nieuwe domein.                                                                                                                       |

---

_Laatst bijgewerkt: 2025-08_
