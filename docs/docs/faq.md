# Veelgestelde vragen

> Antwoorden op de meest voorkomende vragen over myAdmin.

## Algemeen

### Wat is het verschil tussen Test- en Productiemodus?

Testmodus gebruikt een aparte database zodat je veilig kunt oefenen. Productiemodus werkt met je echte financiële gegevens. Zie [Test vs Productie](getting-started/test-vs-production.md) voor meer details.

### Hoe weet ik in welke modus ik zit?

De huidige modus is altijd zichtbaar rechtsboven in de navigatiebalk. **Test** of **Productie** staat duidelijk aangegeven.

### Mijn sessie is verlopen, wat nu?

Sessies verlopen na een periode van inactiviteit. Log gewoon opnieuw in met je gebruikersnaam en wachtwoord. Je werk dat al was opgeslagen gaat niet verloren.

## Bankzaken

### Welk bestandsformaat moet mijn bankafschrift hebben?

myAdmin accepteert CSV-bestanden in Rabobank-formaat. Download het afschrift vanuit je internetbankieren als CSV-bestand.

### Waarom worden sommige transacties als duplicaat gemarkeerd?

Het systeem controleert of een transactie al eerder is geïmporteerd op basis van datum, bedrag en omschrijving. Als een transactie al bestaat, wordt deze als duplicaat gemarkeerd om dubbele boekingen te voorkomen. Zie [Duplicaten afhandelen](banking/handling-duplicates.md).

### Wat doet "Patronen toepassen"?

Deze functie kijkt naar eerder toegewezen rekeningen voor vergelijkbare transacties en past dezelfde toewijzing automatisch toe op nieuwe transacties. Hoe meer je het gebruikt, hoe slimmer het wordt. Zie [Patronen herkenning](banking/pattern-matching.md).

## Facturen

### Hoe werkt de AI-extractie van facturen?

Wanneer je een PDF-factuur uploadt, leest AI de inhoud en haalt automatisch gegevens op zoals leverancier, bedrag, datum en BTW. Je kunt het resultaat altijd controleren en aanpassen voordat je goedkeurt. Zie [AI extractie](invoices/ai-extraction.md).

### Kan ik een factuur bewerken na goedkeuring?

Ja, je kunt goedgekeurde facturen opnieuw openen en bewerken. Ga naar de factuur en klik op **Bewerken**.

### Waar worden mijn facturen opgeslagen?

Facturen worden opgeslagen in Google Drive. myAdmin beheert de mapstructuur automatisch. Zie [Google Drive](invoices/google-drive.md).

## STR (Kortetermijnverhuur)

### Welke platforms worden ondersteund?

myAdmin ondersteunt omzetbestanden van **Airbnb** en **Booking.com**. Zie [Boekingen importeren](str/importing-bookings.md).

### Wat is het verschil tussen gerealiseerde en geplande boekingen?

**Gerealiseerde boekingen** zijn afgeronde verblijven waarvoor je betaling hebt ontvangen. **Geplande boekingen** zijn toekomstige reserveringen die nog moeten plaatsvinden. Zie [Gerealiseerd vs gepland](str/realized-vs-planned.md).

## Belastingen

### Hoe bereid ik mijn BTW-aangifte voor?

Ga naar **Belastingen** → **BTW**, selecteer het kwartaal en controleer de berekende bedragen. Het systeem berekent de BTW op basis van je geïmporteerde transacties en facturen. Zie [BTW aangifte](tax/btw.md).

### Kan ik de belastingberekeningen exporteren?

Ja, alle belastingoverzichten kunnen worden geëxporteerd naar Excel voor je eigen administratie of voor je belastingadviseur.

## Technisch

### De pagina laadt langzaam, wat kan ik doen?

- Ververs de pagina (F5 of Ctrl+R)
- Controleer je internetverbinding
- Probeer een andere browser
- Neem contact op met je beheerder als het probleem aanhoudt

### Ik krijg een foutmelding bij het importeren

Controleer of je bestand het juiste formaat heeft (CSV voor bankafschriften, PDF voor facturen). Probeer het bestand opnieuw te downloaden van de bron. Zie de troubleshooting-sectie van de betreffende module voor specifieke oplossingen.
