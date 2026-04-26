# Draaitabellen (Pivot Views)

> Maak dynamische geaggregeerde overzichten van je data door kolommen te groeperen, aggregatiefuncties te kiezen en filters toe te passen.

## Overzicht

Met Draaitabellen kun je ad-hoc overzichten maken van je financiële transacties of STR-boekingen. Je kiest een databron, selecteert kolommen om op te groeperen, kiest aggregatiefuncties (SUM, COUNT, AVG, MIN, MAX) en past optioneel filters toe. De resultaten worden weergegeven in een sorteerbare tabel die je kunt exporteren naar CSV.

Draaitabellen zijn beschikbaar op twee plekken:

- **Rapportages → Financieel → Pivot Views** — voor financiële transacties
- **Rapportages → BNB → Pivot Views** — voor STR-boekingen

## Opgeslagen modellen gebruiken

In de rapportagetabs werk je met **opgeslagen draaitabelmodellen**. Een beheerder maakt deze modellen aan via [Tenant Beheer → Pivot Views](../tenant-admin/pivot-views.md). Als eindgebruiker kun je:

1. **Model selecteren** — Kies een opgeslagen model uit het dropdown-menu
2. **Filters aanpassen** — Pas filterwaarden aan (bijv. jaar, kwartaal) zonder de modelstructuur te wijzigen
3. **Uitvoeren** — Klik op **Uitvoeren** om de resultaten te bekijken

!!! tip
De modelstructuur (groepkolommen, aggregaties, databron) is vergrendeld. Je kunt alleen de filterwaarden aanpassen. Dit houdt de rapporten consistent.

## Resultaattabel

### Weergavemodi

De resultaattabel ondersteunt drie weergavemodi:

| Modus            | Beschrijving                                                                                  |
| ---------------- | --------------------------------------------------------------------------------------------- |
| **Plat**         | Standaard tabelweergave met één rij per groepscombinatie                                      |
| **Hiërarchisch** | Boomstructuur met inklapbare rijen — eerste groepkolom als topniveau, volgende als subniveaus |
| **Kolom-pivot**  | Waarden van een kolom worden kolomkoppen, aggregaties worden horizontaal verspreid            |

!!! info
De hiërarchische modus is alleen beschikbaar wanneer twee of meer groepkolommen zijn geselecteerd. Bij één groepkolom wordt altijd de platte modus getoond.

### Getalnotatie

Schakel tussen drie getalnotaties via de toggle boven de tabel:

| Notatie   | Voorbeeld   | Beschrijving                   |
| --------- | ----------- | ------------------------------ |
| Decimaal  | € 12.345,67 | Twee decimalen                 |
| Geheel    | € 12.346    | Afgerond op gehele getallen    |
| K-notatie | € 12,3k     | Afgekort met k/M-achtervoegsel |

### Sorteren

Klik op een kolomkop om de resultaten oplopend of aflopend te sorteren. Dit werkt in zowel de platte als hiërarchische modus.

## Exporteren

De resultaattabel biedt twee exportopties:

| Exporttype             | Wat het bevat                                                  |
| ---------------------- | -------------------------------------------------------------- |
| **Pivot resultaat**    | De geaggregeerde data zoals weergegeven in de tabel            |
| **Onderliggende data** | Alle individuele rijen vóór aggregatie, met volledige precisie |

### Stap voor stap: Exporteren

1. Voer eerst een draaitabel uit zodat er resultaten zijn
2. Klik op de **Export** knop
3. Kies **Pivot resultaat** of **Onderliggende data**
4. Het CSV-bestand wordt automatisch gedownload

!!! note
De exportknoppen zijn uitgeschakeld wanneer er geen data is. Voer eerst een query uit.

## Beschikbare databronnen

Welke databronnen beschikbaar zijn hangt af van de module:

| Module     | Databron               | Beschrijving                  |
| ---------- | ---------------------- | ----------------------------- |
| Financieel | Financial Transactions | Financiële transacties        |
| BNB        | STR Revenue            | Kortetermijnverhuur boekingen |

!!! info
De systeembeheerder kan extra databronnen inschakelen via het SysAdmin-dashboard. Neem contact op met je beheerder als je een databron mist.

## Problemen oplossen

| Probleem                  | Oorzaak                                   | Oplossing                                       |
| ------------------------- | ----------------------------------------- | ----------------------------------------------- |
| Geen modellen zichtbaar   | Geen modellen aangemaakt voor deze module | Vraag je Tenant Admin om een model aan te maken |
| Geen data na uitvoeren    | Filters te restrictief                    | Pas de filterwaarden aan of verwijder filters   |
| "Column not allowed" fout | Kolom niet beschikbaar voor je tenant     | Neem contact op met je beheerder                |
| Export knop uitgeschakeld | Geen resultaten geladen                   | Voer eerst een draaitabel uit                   |
| Tabel laadt langzaam      | Grote dataset of veel groepkolommen       | Gebruik filters om de dataset te beperken       |
