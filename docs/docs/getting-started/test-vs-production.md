# Test vs Productie

> Wanneer gebruik je welke modus en wat is het verschil?

## Overzicht

myAdmin heeft twee modi: **Testmodus** en **Productiemodus**. Elke modus gebruikt een eigen database, zodat je veilig kunt oefenen zonder echte gegevens te beïnvloeden.

## Wat is het verschil?

|                   | Testmodus                          | Productiemodus                       |
| ----------------- | ---------------------------------- | ------------------------------------ |
| **Database**      | Aparte testdatabase                | Productiedatabase met echte gegevens |
| **Gegevens**      | Voorbeelddata of je eigen testdata | Echte financiële gegevens            |
| **Risico**        | Geen — je kunt niets kapotmaken    | Wijzigingen zijn definitief          |
| **Geschikt voor** | Leren, testen, uitproberen         | Dagelijks werk                       |

## Wanneer gebruik je Testmodus?

- Je bent **nieuw** en wilt het platform leren kennen
- Je wilt een **nieuwe functie** uitproberen voordat je het op echte data toepast
- Je wilt **importbestanden testen** om te zien of het formaat klopt
- Je wilt **patronen testen** zonder echte transacties te wijzigen

## Wanneer gebruik je Productiemodus?

- Je verwerkt **echte bankafschriften**
- Je uploadt **echte facturen**
- Je bereidt **belastingaangiften** voor
- Je genereert **rapportages** voor je administratie

## Hoe schakel je tussen modi?

1. Kijk rechtsboven in de applicatie
2. Je ziet een schakelaar met **Test** of **Productie**
3. Klik op de schakelaar om van modus te wisselen
4. De pagina herlaadt met gegevens uit de geselecteerde database

!!! danger
Wees voorzichtig bij het overschakelen naar **Productiemodus**. Alle wijzigingen die je maakt (importeren, verwijderen, bewerken) zijn definitief en werken op echte gegevens.

!!! tip
Twijfel je? Blijf in **Testmodus**. Je kunt altijd later overschakelen naar productie.

## Tips

- De huidige modus is altijd zichtbaar in de navigatiebalk
- Testdata en productiedata zijn volledig gescheiden
- Je kunt in testmodus dezelfde bestanden importeren als in productie — het raakt alleen de testdatabase

## Problemen oplossen

| Probleem                  | Oorzaak                                              | Oplossing                                               |
| ------------------------- | ---------------------------------------------------- | ------------------------------------------------------- |
| Ik zie geen data          | Je zit in testmodus en er is nog geen testdata       | Importeer eerst testbestanden of schakel naar productie |
| Mijn wijzigingen zijn weg | Je hebt in testmodus gewerkt in plaats van productie | Herhaal de actie in productiemodus                      |
| Kan niet schakelen        | Onvoldoende rechten                                  | Neem contact op met je beheerder                        |
