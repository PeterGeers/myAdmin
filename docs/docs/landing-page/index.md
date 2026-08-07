# Landing Page

## Overzicht

Met de Landing Page functie maak je een professionele publieke webpagina voor je bedrijf. De pagina wordt gehost op een snel CDN (CloudFront) en is bereikbaar via een unieke URL. Bezoekers kunnen je pagina bekijken zonder in te loggen.

## Slug instellen

De slug is het unieke deel van je pagina-URL (bijv. `mijn-bedrijf` → `https://d3afn46os9e9nc.cloudfront.net/mijn-bedrijf`).

1. Ga naar **Tenant Admin** → **Landing Page** tab
2. Vul een slug in (alleen kleine letters, cijfers en streepjes, minimaal 3 tekens)
3. Klik **Save**

!!! note "Slug wijzigen"
Na het instellen kun je de slug wijzigen. Publiceer daarna opnieuw om de URL bij te werken.

## Blocks toevoegen en bewerken

Je pagina bestaat uit blokken die je kunt toevoegen, verwijderen en herordenen.

### Beschikbare block types

| Type         | Beschrijving                                               |
| ------------ | ---------------------------------------------------------- |
| Hero         | Hoofdsectie met titel, ondertitel, afbeelding en actieknop |
| About        | Tekst met optionele afbeelding                             |
| Gallery      | Fotogalerij                                                |
| Testimonials | Klantervaringen/reviews                                    |
| FAQ          | Veelgestelde vragen (accordion)                            |
| Pricing      | Tarieven/pakketten                                         |
| CTA          | Call-to-action banner                                      |
| Embed        | Externe widget (iframe, bijv. boekingswidget)              |
| Contact      | Contactformulier                                           |
| Services     | ZZP diensten (alleen bij actieve ZZP module)               |

### Blocks beheren

1. Klik **+ Add Block** om een nieuw blok toe te voegen
2. Kies het type en een layout variant
3. Klik op een blok om de instellingen te bewerken (rechterpaneel)
4. Gebruik de pijltjes om blokken te herordenen
5. Gebruik het prullenbak-icoon om een blok te verwijderen

Wijzigingen worden automatisch opgeslagen (auto-save).

## Afbeeldingen uploaden

Afbeeldingen upload je via drag-and-drop of klik op het uploadgebied.

- **Toegestane formaten:** JPG, PNG, WebP, SVG
- **Maximale grootte:** 5 MB
- Afbeeldingen worden opgeslagen in de cloud en direct beschikbaar via een snelle URL

## Branding & Social Links

Ga naar de **Branding** tab om je bedrijfsgegevens in te stellen:

- **Logo** — upload je bedrijfslogo
- **Bedrijfsnaam & tagline** — verschijnt in de header
- **Kleuren** — primaire kleur en accentkleur voor je pagina
- **Contactgegevens** — adres, telefoon, e-mail, KVK, BTW
- **Social media** — links naar Instagram, Facebook, LinkedIn, Airbnb, Booking.com, YouTube, TikTok, X/Twitter
- **Deelknoppen** — schakel in/uit of bezoekers je pagina kunnen delen

!!! tip "Vergeet niet op te slaan"
Klik op de **Opslaan** knop bovenaan na het wijzigen van branding gegevens.

## SEO instellingen & OG image

Ga naar de **SEO** tab om te bepalen hoe je pagina verschijnt in zoekresultaten en bij het delen op social media:

- **SEO Titel** — de titel die verschijnt in Google en bij het delen (max 60 tekens)
- **SEO Beschrijving** — korte omschrijving voor zoekresultaten (max 155 tekens)
- **OG Image** — afbeelding die verschijnt bij het delen op social media (aanbevolen: 1200×630 pixels)

De OG preview card toont hoe je link eruit ziet als iemand hem deelt.

## Publiceren & offline halen

### Publiceren

1. Voeg minstens één blok toe
2. Klik op de groene **Publish** knop
3. Je pagina is direct zichtbaar op je URL

Bij elke publicatie wordt een versie-snapshot bewaard zodat je kunt terugdraaien.

### Offline halen

Klik op **Unpublish** om je pagina offline te halen. Bezoekers zien dan een 404-pagina. Je concept (draft) blijft bewaard.

## Contactformulier

Als je een Contact-blok hebt toegevoegd, kunnen bezoekers je berichten sturen.

- Berichten worden opgeslagen in de database
- Je ontvangt een e-mail notificatie op het adres ingesteld bij Branding
- **Spambeveiliging:** maximaal 5 berichten per e-mailadres per uur
- **Bot-bescherming:** honeypot veld (onzichtbaar voor echte bezoekers)

## Deelknoppen

Wanneer ingeschakeld (via Branding → Deelknoppen), zien bezoekers knoppen om je pagina te delen via:

- Facebook
- X/Twitter
- WhatsApp
- LinkedIn
- E-mail

Er worden geen externe scripts geladen — alleen standaard deel-URLs.
