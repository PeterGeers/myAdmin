# Exporteren

> De getoonde leden exporteren naar een CSV-bestand.

## Overzicht

Je exporteert de leden uit het Leden Overzicht naar een CSV-bestand, bijvoorbeeld voor verdere verwerking in een spreadsheet. De export bevat de leden die binnen jouw regiobereik vallen.

## Wat je nodig hebt

- `Members_Export` recht
- De exportknop in het Leden Overzicht is bovendien alleen zichtbaar voor **Tenant Admin** en **SysAdmin**

!!! info
De exportknop in het overzicht is bewust beperkt tot Tenant Admin en SysAdmin: dit is een volledige CSV-dump van de ledentabel. Wil je als gewone gebruiker een gefilterde of samengevatte export, gebruik dan de rapportage-/draaitabelweergaven, die rijkere exports bieden.

## Stap voor stap

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Klik op **Exporteren**
3. Er wordt een CSV-bestand gedownload (bestandsnaam `leden-JJJJ-MM-DD.csv`)

!!! info
De export bevat **alle** leden binnen jouw regiobereik — niet alleen de rijen die je op dat moment in de tabel hebt gefilterd of gezocht. Het bereik wordt aan de serverzijde afgedwongen: een gebruiker met bereik over alleen Noord exporteert uitsluitend Noord-leden. Zie [Overzicht](index.md) voor uitleg over regiobereik.

!!! tip
Wil je een gefilterde of samengevatte export (bijvoorbeeld per status of lidmaatschapstype), gebruik dan de rapportage-/draaitabelweergaven. Het Leden Overzicht exporteert altijd de volledige, binnen je bereik zichtbare lijst.

## Wat staat er in het bestand?

De CSV bevat één kolom per zichtbaar veld uit de veldconfiguratie van je tenant (vaste velden, extra velden en berekende velden), met het echte lidnummer. Het interne technische lid-id en systeemtijdstempels worden niet geëxporteerd.

## Problemen oplossen

| Probleem                        | Oorzaak                                | Oplossing                                                  |
| ------------------------------- | -------------------------------------- | ---------------------------------------------------------- |
| Knop **Exporteren** ontbreekt   | Je hebt geen `Members_Export` recht, of je bent geen Tenant Admin / SysAdmin | Vraag je Tenant Admin om het exportrecht of een exportrol |
| Export bevat minder leden dan verwacht | Je regiobereik is beperkt         | Controleer je regiobereik met je Tenant Admin              |
| Je mist een filterbare export   | Het overzicht exporteert de hele lijst | Gebruik de rapportage-/draaitabelweergaven voor een gefilterde export |
