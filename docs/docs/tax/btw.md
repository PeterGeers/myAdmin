# BTW aangifte

> Kwartaalaangifte omzetbelasting (BTW) voorbereiden en opslaan.

## Overzicht

Het BTW-rapport berekent je omzetbelasting per kwartaal op basis van je financiële transacties. Het toont de ontvangen BTW, de voorbelasting (betaalde BTW) en het verschil dat je moet betalen of terugkrijgt.

## Wat je nodig hebt

- Geïmporteerde transacties voor het betreffende kwartaal
- Toegang tot financiële rapporten (`Finance_Read` rechten)
- Een geselecteerde tenant/administratie

## Hoe werkt de berekening?

Het systeem berekent drie onderdelen:

| Onderdeel            | Beschrijving                                       | Rekeningen               |
| -------------------- | -------------------------------------------------- | ------------------------ |
| Saldo BTW-rekeningen | Lopend saldo van BTW-rekeningen tot einde kwartaal | 2010, 2020, 2021         |
| Ontvangen BTW        | BTW die je hebt ontvangen over je omzet            | Omzet- en BTW-rekeningen |
| Voorbelasting        | BTW die je hebt betaald op inkopen                 | Voorbelasting-rekeningen |

**Eindberekening:**

```
Te betalen = Ontvangen BTW − Voorbelasting
```

- Positief resultaat → Je moet BTW betalen aan de Belastingdienst
- Negatief resultaat → Je krijgt BTW terug van de Belastingdienst

## Stap voor stap

### 1. Open het BTW-rapport

Ga naar **Rapportages** → **Financieel** → **BTW**.

### 2. Selecteer jaar en kwartaal

Kies het jaar en het kwartaal (Q1–Q4) waarvoor je de aangifte wilt voorbereiden.

| Kwartaal | Periode            | Einddatum    |
| -------- | ------------------ | ------------ |
| Q1       | Januari – Maart    | 31 maart     |
| Q2       | April – Juni       | 30 juni      |
| Q3       | Juli – September   | 30 september |
| Q4       | Oktober – December | 31 december  |

### 3. Genereer het rapport

Klik op **Genereer rapport**. Het systeem:

1. Berekent het saldo van de BTW-rekeningen tot het einde van het kwartaal
2. Berekent de ontvangen BTW en voorbelasting voor het kwartaal
3. Toont het resultaat: te betalen of terug te ontvangen

### 4. Bekijk het rapport

Het rapport toont twee secties:

**Saldo-overzicht:**

- BTW-rekeningen met hun saldi tot het einde van het kwartaal
- Totaal saldo

**Kwartaaloverzicht:**

- BTW- en omzetrekeningen voor het specifieke kwartaal
- Ontvangen BTW
- Voorbelasting (betaalde BTW)
- Betalingsinstructie ("€X te betalen" of "€X terug te ontvangen")

### 5. Sla de transactie op

Klik op **Opslaan** om de BTW-transactie vast te leggen in de database. Het rapport wordt ook geüpload als HTML-bestand.

## Exporteren

- Het rapport wordt automatisch opgeslagen als HTML-bestand: `BTW_[Administratie]_[Jaar]_Q[Kwartaal].html`
- Je kunt het HTML-bestand printen of opslaan voor je administratie

## Tips

!!! tip
Genereer het BTW-rapport pas nadat alle transacties van het kwartaal zijn geïmporteerd. Ontbrekende transacties leiden tot een onjuiste berekening.

- Controleer altijd het resultaat voordat je de aangifte indient bij de Belastingdienst
- Het systeem houdt rekening met het juiste BTW-tarief (9% of 21%) op basis van de transactiedatum
- Bewaar het HTML-rapport voor je eigen administratie

## Problemen oplossen

| Probleem              | Oorzaak                                   | Oplossing                                                |
| --------------------- | ----------------------------------------- | -------------------------------------------------------- |
| Rapport is leeg       | Geen transacties in het kwartaal          | Importeer eerst de transacties voor dit kwartaal         |
| BTW-bedrag klopt niet | Transacties ontbreken of verkeerd geboekt | Controleer of alle transacties correct zijn geïmporteerd |
| "No tenant selected"  | Geen administratie geselecteerd           | Selecteer een tenant in de navigatiebalk                 |
| Opslaan mislukt       | Geen schrijfrechten                       | Neem contact op met je beheerder                         |
