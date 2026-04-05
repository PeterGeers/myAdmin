# Google Drive

> Factuurbestanden beheren in Google Drive.

## Overzicht

Alle geüploade facturen worden automatisch opgeslagen in Google Drive. Het systeem organiseert bestanden per leverancier in een mappenstructuur die per administratie (tenant) is gescheiden.

## Hoe werkt het?

### Mappenstructuur

Bestanden worden opgeslagen in de volgende structuur:

```
Google Drive/
└── [Administratie]/
    └── Facturen/
        ├── Amazon/
        │   ├── factuur-2026-001.pdf
        │   └── factuur-2026-002.pdf
        ├── Booking.com/
        │   └── commission-march-2026.pdf
        ├── Eneco/
        │   └── jaarnota-2025.pdf
        └── [Leverancier]/
            └── [bestand].pdf
```

- Elke administratie heeft een eigen hoofdmap
- Binnen de hoofdmap is er een map per leverancier
- Bestanden worden automatisch in de juiste leveranciersmap geplaatst

### Koppeling met transacties

Wanneer een factuur wordt verwerkt, slaat het systeem de Google Drive-link op in het **Ref3**-veld van de transactie. Hierdoor kun je vanuit elke transactie direct het originele bestand openen.

## Stap voor stap

### Bestand openen vanuit een transactie

1. Ga naar **Bankzaken** of bekijk een transactie
2. Klik op het **Ref3**-veld (bevat de Google Drive-URL)
3. Het bestand opent in een nieuw tabblad in Google Drive

### Nieuwe leveranciersmap aanmaken

1. Ga naar **Facturen**
2. Klik op **Nieuwe map aanmaken**
3. Voer de naam van de leverancier in
4. De map wordt aangemaakt in Google Drive en verschijnt in de mappenlijst

## Authenticatie

Google Drive-toegang wordt per administratie geconfigureerd door je beheerder. Het systeem gebruikt OAuth-authenticatie om veilig verbinding te maken met Google Drive.

!!! info
Als de Google Drive-verbinding verloopt, verschijnt er een melding in de applicatie. Neem contact op met je beheerder om de verbinding te vernieuwen.

## Tips

- Alle bestanden zijn ook direct toegankelijk via Google Drive in je browser
- De mappenstructuur wordt automatisch beheerd — je hoeft zelf geen mappen aan te maken
- Bestanden worden niet verwijderd uit Google Drive als je een transactie verwijdert

## Problemen oplossen

| Probleem                                   | Oorzaak                                                 | Oplossing                                        |
| ------------------------------------------ | ------------------------------------------------------- | ------------------------------------------------ |
| "Google Drive OAuth credentials not found" | Geen credentials geconfigureerd voor deze administratie | Neem contact op met je beheerder                 |
| Link opent niet                            | Google Drive-sessie verlopen                            | Log opnieuw in bij Google Drive in je browser    |
| Bestand niet gevonden                      | Bestand is verplaatst of verwijderd in Google Drive     | Controleer de prullenbak in Google Drive         |
| Upload mislukt                             | Onvoldoende opslagruimte                                | Controleer de beschikbare ruimte in Google Drive |
