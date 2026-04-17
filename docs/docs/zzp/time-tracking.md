# Urenregistratie

> Gewerkte uren bijhouden per klant en project.

## Overzicht

Met de urenregistratie houd je bij hoeveel uur je werkt per klant en project. Je kunt uren markeren als factureerbaar of niet-factureerbaar, en factureerbare uren direct omzetten naar factuurregels. Zo weet je altijd precies wat je nog moet factureren.

!!! info
De urenregistratie kan per tenant worden in- of uitgeschakeld via de instellingen. Als je de urenregistratie niet ziet, vraag dan je Tenant Admin om deze functie te activeren.

## Wat je nodig hebt

- Toegang tot de ZZP-module (`zzp_crud` rechten)
- Minimaal één contact in je contactenregister
- Optioneel: producten gekoppeld aan uurtarieven

## Stap voor stap

### 1. Uren registreren

1. Ga naar **ZZP** → **Urenregistratie**
2. Klik op **Nieuwe registratie**
3. Vul de velden in:

| Veld           | Verplicht | Beschrijving                                           |
| -------------- | --------- | ------------------------------------------------------ |
| Datum          | Ja        | Datum waarop de uren zijn gewerkt                      |
| Contact        | Ja        | De klant waarvoor je hebt gewerkt                      |
| Uren           | Ja        | Aantal gewerkte uren (decimaal, bijv. 7.5)             |
| Uurtarief      | Ja        | Tarief per uur (excl. BTW)                             |
| Product/dienst | Nee       | Koppeling aan een product uit je catalogus             |
| Projectnaam    | Nee       | Naam van het project                                   |
| Omschrijving   | Nee       | Beschrijving van de werkzaamheden                      |
| Factureerbaar  | Nee       | Of deze uren gefactureerd mogen worden (standaard: ja) |

4. Klik op **Opslaan**

!!! tip
Koppel je uren aan een product uit je catalogus. Zo worden het uurtarief en de BTW-code automatisch ingevuld.

### 2. Factuur aanmaken vanuit uren

1. Ga naar **ZZP** → **Urenregistratie**
2. Filter op het gewenste contact en de periode
3. Selecteer de uren die je wilt factureren (alleen niet-gefactureerde, factureerbare uren)
4. Klik op **Factuur aanmaken**
5. De geselecteerde uren worden omgezet naar factuurregels
6. Controleer de factuur en klik op **Opslaan**

Wanneer uren aan een factuur zijn gekoppeld, worden ze gemarkeerd als "gefactureerd" en verschijnen ze niet meer in de lijst van te factureren uren.

### 3. Overzichten bekijken

De urenregistratie biedt samenvattingen per:

| Overzicht   | Beschrijving                                  |
| ----------- | --------------------------------------------- |
| Per klant   | Totaal uren en bedrag per contact             |
| Per project | Totaal uren en bedrag per projectnaam         |
| Per periode | Totaal uren per week, maand, kwartaal of jaar |

1. Ga naar **ZZP** → **Urenregistratie**
2. Gebruik de filters om de gewenste periode en klant te selecteren
3. Bekijk de samenvattingen onderaan het overzicht

### 4. Ondersteunende documenten uploaden

Je kunt documenten koppelen aan je urenregistratie:

1. Open een urenregistratie of factuur
2. Klik op **Document uploaden**
3. Selecteer het bestand (bijv. urenstaat van de klant, contract, leveringsbevestiging)
4. Het document wordt opgeslagen en gekoppeld

!!! info
Gekoppelde documenten kun je meesturen als bijlage bij het versturen van een factuur. Zie [Facturen versturen](sending-invoices.md) voor meer informatie.

## Factureerbaar vs niet-factureerbaar

| Type               | Beschrijving                                     |
| ------------------ | ------------------------------------------------ |
| Factureerbaar      | Uren die je aan de klant in rekening brengt      |
| Niet-factureerbaar | Uren voor interne taken, acquisitie of opleiding |

Niet-factureerbare uren worden niet meegenomen bij het aanmaken van facturen, maar zijn wel zichtbaar in je overzichten voor je eigen administratie.

## Tips

!!! tip
Registreer je uren dagelijks of wekelijks. Zo voorkom je dat je uren vergeet en kun je aan het einde van de maand snel een factuur aanmaken.

- Gebruik projectnamen consistent zodat je overzichten per project kunt bekijken
- Het uurtarief kan per registratie afwijken van het standaardtarief in je productcatalogus
- Niet-gefactureerde uren blijven zichtbaar totdat je ze aan een factuur koppelt

## Problemen oplossen

| Probleem                             | Oorzaak                                         | Oplossing                                                  |
| ------------------------------------ | ----------------------------------------------- | ---------------------------------------------------------- |
| Urenregistratie niet zichtbaar       | Functie is uitgeschakeld voor je tenant         | Vraag je Tenant Admin om urenregistratie in te schakelen   |
| Uren verschijnen niet bij factureren | Uren zijn al gefactureerd of niet-factureerbaar | Controleer de status en het factureerbaar-vlag van de uren |
| Geen contacten beschikbaar           | Nog geen contacten aangemaakt                   | Maak eerst een contact aan via [Contacten](contacts.md)    |
