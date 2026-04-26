# Draaitabelmodellen beheren

> Maak, bewerk en verwijder draaitabelmodellen die beschikbaar zijn voor gebruikers in je organisatie.

## Overzicht

Als Tenant Admin maak je draaitabelmodellen aan die je gebruikers kunnen gebruiken in de rapportagetabs. Een model definieert de structuur van een draaitabel: welke databron, welke groepkolommen, welke aggregaties en welke standaardfilters. Gebruikers kunnen vervolgens alleen de filterwaarden aanpassen — de structuur blijft vergrendeld.

Draaitabelmodellen beheer je via **Tenant Beheer** → **Pivot Views**.

## Een model aanmaken

### Stap voor stap

1. Ga naar **Tenant Beheer** → **Pivot Views**
2. Selecteer een **databron** uit het dropdown-menu (bijv. Financial Transactions, STR Revenue)
3. Kies **groepkolommen** — de kolommen waarop gegroepeerd wordt (max. 5)
4. Kies **aggregatiematen** — combinatie van functie (SUM, COUNT, AVG, MIN, MAX) en kolom (max. 10)
5. Stel optioneel **filters** in als standaardwaarden
6. Configureer optioneel een **kolom-pivot** en **nestniveaus**
7. Klik op **Uitvoeren** om een voorbeeld te bekijken
8. Klik op **Opslaan** en geef het model een naam

!!! warning
Modelnamen moeten uniek zijn binnen je tenant. Als je een bestaande naam gebruikt, krijg je een foutmelding.

### Groepkolommen kiezen

Groepkolommen bepalen hoe de data wordt opgesplitst. Voorbeelden:

| Groepering                   | Resultaat                                       |
| ---------------------------- | ----------------------------------------------- |
| `jaar`                       | Eén rij per jaar                                |
| `jaar`, `kwartaal`           | Eén rij per jaar-kwartaal combinatie            |
| `channel`, `listing`, `year` | Eén rij per kanaal-accommodatie-jaar combinatie |

### Aggregatiematen kiezen

Aggregatiematen berekenen waarden per groep:

| Functie | Beschrijving | Voorbeeld                  |
| ------- | ------------ | -------------------------- |
| SUM     | Optellen     | SUM(Amount) — totaalbedrag |
| COUNT   | Tellen       | COUNT(\*) — aantal rijen   |
| AVG     | Gemiddelde   | AVG(pricePerNight)         |
| MIN     | Minimum      | MIN(Amount)                |
| MAX     | Maximum      | MAX(amountGross)           |

### Kolom-pivot configureren

Met een kolom-pivot worden de waarden van een kolom omgezet naar kolomkoppen:

1. Selecteer een kolom als **Kolom Pivot** (bijv. `jaar`)
2. Voeg optioneel **nestniveaus** toe (bijv. `kwartaal` onder `jaar`)
3. De resultaattabel toont dan kolommen per jaar, met subkolommen per kwartaal

!!! info
Een kolom kan niet tegelijk als groepkolom, kolom-pivot én nestniveau worden gebruikt.

## Modellen bewerken

1. Selecteer een bestaand model uit de **Laden** dropdown
2. Pas de configuratie aan
3. Klik op **Opslaan** — het model wordt bijgewerkt met dezelfde naam

## Modellen verwijderen

1. Selecteer het model uit de **Laden** dropdown
2. Klik op **Verwijderen**
3. Bevestig de verwijdering

!!! warning
Verwijderde modellen zijn niet meer beschikbaar voor gebruikers in de rapportagetabs.

## Weergavemodi

Bij het aanmaken van een model kun je de standaard weergavemodus instellen:

| Modus            | Wanneer gebruiken                                                |
| ---------------- | ---------------------------------------------------------------- |
| **Plat**         | Eenvoudige tabel, geschikt voor 1 groepkolom                     |
| **Hiërarchisch** | Boomstructuur met inklapbare rijen, ideaal voor 2+ groepkolommen |

De weergavemodus kan door de eindgebruiker worden gewisseld zonder de query opnieuw uit te voeren.

## Kolomtoegang

Welke kolommen beschikbaar zijn wordt bepaald door twee niveaus:

1. **Systeemniveau** — De systeembeheerder bepaalt welke kolommen per databron beschikbaar zijn
2. **Tenantniveau** — Als Tenant Admin kun je de beschikbare kolommen verder beperken via **Instellingen** → **Parameters** (namespace `ui.pivot`)

!!! tip
Als je een kolom mist, controleer dan de parameter `allowed_columns.<databron>` in je tenant-instellingen. De systeembeheerder kan ook kolommen hebben uitgesloten op systeemniveau.

## Problemen oplossen

| Probleem                        | Oorzaak                                    | Oplossing                                           |
| ------------------------------- | ------------------------------------------ | --------------------------------------------------- |
| "Name already exists" fout      | Modelnaam is al in gebruik                 | Kies een andere naam of bewerk het bestaande model  |
| Geen databronnen beschikbaar    | Geen bronnen ingeschakeld door SysAdmin    | Neem contact op met de systeembeheerder             |
| Kolom niet zichtbaar            | Kolom uitgesloten of beperkt               | Controleer de `allowed_columns` parameter           |
| Model niet zichtbaar in rapport | Databron heeft geen module-tag             | Neem contact op met de systeembeheerder             |
| Validatiefout bij opslaan       | Geen groepkolom of aggregatie geselecteerd | Selecteer minimaal 1 groepkolom en 1 aggregatiemaat |
