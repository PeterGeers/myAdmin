# Exporteren

> De getoonde leden exporteren naar een CSV-bestand.

## Overzicht

Je exporteert de leden uit het Leden Overzicht naar een CSV-bestand, bijvoorbeeld voor verdere verwerking in een spreadsheet. De export bevat de rijen die op dat moment worden getoond en die binnen jouw regiobereik vallen.

## Wat je nodig hebt

- `Members_Export` recht

## Stap voor stap

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Stel eventueel filters in om de gewenste selectie te tonen (zie [Filteren & weergave](filters-and-views.md))
3. Klik op **Exporteren**
4. Er wordt een CSV-bestand gedownload met de getoonde leden

!!! info
De export volgt wat je ziet: alleen de rijen binnen jouw regiobereik worden geëxporteerd, en actieve filters bepalen mee welke rijen in het bestand terechtkomen. Een gebruiker met bereik over alleen Noord exporteert dus uitsluitend Noord-leden. Zie [Overzicht](index.md) voor uitleg over regiobereik.

!!! tip
Wil je een subset exporteren, filter dan eerst op bijvoorbeeld regio, status of lidmaatschapstype. Alleen de gefilterde rijen komen in de CSV.

## Problemen oplossen

| Probleem                        | Oorzaak                                | Oplossing                                                  |
| ------------------------------- | -------------------------------------- | ---------------------------------------------------------- |
| Knop **Exporteren** ontbreekt   | Je hebt geen `Members_Export` recht    | Vraag je Tenant Admin om het exportrecht                   |
| Export bevat minder leden dan verwacht | Er staat nog een filter aan of je bereik is beperkt | Wis filters; controleer je regiobereik met je Tenant Admin |
