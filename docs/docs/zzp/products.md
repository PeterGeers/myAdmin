# Producten & diensten

> Je product- en dienstencatalogus beheren.

## Overzicht

In de productcatalogus beheer je alle producten en diensten die je op facturen kunt plaatsen. Elk product heeft een prijs, BTW-code en type. Wanneer je een factuur aanmaakt, kun je snel regelitems toevoegen vanuit je catalogus.

## Wat je nodig hebt

- Toegang tot de ZZP-module (`zzp_crud` rechten)
- Een productnaam en productcode voor elk item

## Stap voor stap

### 1. Product aanmaken

1. Ga naar **ZZP** → **Producten**
2. Klik op **Nieuw product**
3. Vul de velden in:

| Veld               | Verplicht | Beschrijving                                          |
| ------------------ | --------- | ----------------------------------------------------- |
| Productcode        | Ja        | Unieke code (bijv. "CONSULT", "DEV-UUR")              |
| Naam               | Ja        | Naam van het product of de dienst                     |
| Type               | Ja        | Producttype (bijv. dienst, product, uren, abonnement) |
| Eenheidsprijs      | Ja        | Standaardprijs per eenheid (excl. BTW)                |
| BTW-code           | Ja        | Hoog (21%), laag (9%) of nul (0%)                     |
| Omschrijving       | Nee       | Uitgebreide beschrijving                              |
| Eenheid            | Nee       | Eenheid van meting (bijv. uur, stuk, maand)           |
| Externe referentie | Nee       | Referentie naar extern systeem                        |

4. Klik op **Opslaan**

!!! tip
Gebruik duidelijke productcodes die je snel herkent op facturen. Bijvoorbeeld "CONSULT-UUR" voor consultancy-uren of "HOSTING-MND" voor maandelijkse hosting.

### 2. BTW-code instellen

Elk product moet een BTW-code hebben. De beschikbare codes zijn:

| BTW-code | Tarief | Wanneer gebruiken                                 |
| -------- | ------ | ------------------------------------------------- |
| Hoog     | 21%    | Standaard voor de meeste diensten en producten    |
| Laag     | 9%     | Verlaagd tarief (bijv. bepaalde voedingsmiddelen) |
| Nul      | 0%     | Vrijgesteld of verlegd (bijv. export buiten EU)   |

!!! info
BTW-tarieven worden automatisch bepaald op basis van de factuurdatum via de belastingtarieven in je administratie.

### 3. Product bewerken

1. Ga naar **ZZP** → **Producten**
2. Klik op het product dat je wilt bewerken
3. Pas de gewenste velden aan
4. Klik op **Opslaan**

### 4. Product verwijderen

1. Ga naar **ZZP** → **Producten**
2. Klik op het product dat je wilt verwijderen
3. Klik op **Verwijderen**

!!! warning
Producten die gekoppeld zijn aan bestaande factuurregels kunnen niet worden verwijderd. Deactiveer het product in plaats daarvan zodat het niet meer beschikbaar is voor nieuwe facturen.

## Producttypen

De beschikbare producttypen zijn instelbaar per tenant. Standaard zijn de volgende typen beschikbaar:

| Type       | Beschrijving                    |
| ---------- | ------------------------------- |
| Dienst     | Geleverde dienstverlening       |
| Product    | Fysiek of digitaal product      |
| Uren       | Uurtarief-gebaseerde dienst     |
| Abonnement | Terugkerende dienst of licentie |

!!! info
Je Tenant Admin kan extra producttypen toevoegen via de instellingen zonder dat er technische wijzigingen nodig zijn.

## Tips

!!! tip
Maak een product aan voor elke dienst die je regelmatig factureert. Zo hoef je bij het aanmaken van een factuur alleen het product te selecteren en de hoeveelheid in te vullen.

- Houd je productcodes kort en consistent
- Gebruik het type "Uren" voor producten die je koppelt aan urenregistratie
- De eenheidsprijs is de standaardprijs — je kunt deze per factuurregel overschrijven

## Problemen oplossen

| Probleem                           | Oorzaak                                    | Oplossing                                              |
| ---------------------------------- | ------------------------------------------ | ------------------------------------------------------ |
| "Productcode bestaat al"           | Productcode is niet uniek binnen je tenant | Kies een andere productcode                            |
| Product kan niet verwijderd worden | Product is gekoppeld aan factuurregels     | Deactiveer het product in plaats van verwijderen       |
| BTW-code niet beschikbaar          | Belastingtarieven niet geconfigureerd      | Vraag je Tenant Admin om de BTW-tarieven in te stellen |
