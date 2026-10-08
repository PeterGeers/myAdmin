# Afzender verifiëren

> Een afzender-e-mailadres toevoegen en verifiëren, zodat je tenant vanuit een eigen adres mag mailen.

## Overzicht

Voordat je organisatie mail kan versturen vanuit myAdmin (bijvoorbeeld de ledenmailings en bezorgingen uit de [Ledenadministratie](../members/delivery.md)), moet je als Tenant Admin één keer een **afzenderadres** toevoegen en **verifiëren**. Pas als een afzender is geverifieerd en je tenant is **vrijgegeven om te mailen**, verschijnen de mailacties voor je gebruikers.

!!! info
De mailacties in de modules (zoals **Mailen**, een bezorging en inplannen in de Ledenadministratie) zijn **verborgen** zolang je tenant niet is vrijgegeven. Zodra de vrijgave er is, verschijnen ze vanzelf.

## Een afzender toevoegen en verifiëren

1. Ga in **Tenant Beheer** naar het onderdeel **Afzenders** (afzenderverificatie).
2. Voer het **afzender-e-mailadres** in dat je wilt gebruiken (een adres dat je organisatie beheert).
3. Bevestig; het systeem start de verificatie en stuurt een **verificatiemail** naar dat adres.
4. Open die mail en volg de bevestigingslink.
5. Terug in de lijst verandert de **status** van het adres naar *geverifieerd*.

!!! info
De verificatie bevestigt dat je organisatie het adres daadwerkelijk beheert. Dit is een eenmalige stap per afzenderadres.

!!! tip
Gebruik een adres dat je team ook echt kan ontvangen (bijvoorbeeld een gedeelde postbus), zodat je de bevestigingslink kunt openen. Een no-reply-adres zonder postvak kan de verificatiemail niet ontvangen.

## De vrijgave om te mailen (mail-vrijgave)

Naast een geverifieerde afzender geldt een per-tenant **vrijgave om te verzenden**. Deze vrijgave bepaalt of de mailacties voor je tenant worden aangeboden:

- Is je tenant **niet** vrijgegeven, dan zien je gebruikers de mailacties niet.
- Is je tenant **wel** vrijgegeven en is er een geverifieerde afzender, dan kunnen gebruikers mailen, een bezorging instellen en (bij voldoende rechten) inplannen.

!!! info
De vrijgave en de geverifieerde afzender horen bij elkaar: de verzonden mail gaat uit vanaf jouw geverifieerde afzenderadres.

## Status van een afzender

In de lijst zie je per afzender de status:

| Status       | Betekenis                                                           |
| ------------ | ------------------------------------------------------------------- |
| In afwachting | De verificatiemail is verstuurd; de bevestigingslink is nog niet gevolgd |
| Geverifieerd  | Het adres is bevestigd en kan als afzender worden gebruikt          |

## Rechten

| Recht          | Wat de gebruiker kan                                        |
| -------------- | ----------------------------------------------------------- |
| `Tenant_Admin` | Afzenderadressen toevoegen en verifiëren voor de tenant     |

!!! info
Afzenderverificatie is voorbehouden aan de **Tenant Admin**. Gewone gebruikers kunnen geen afzenders toevoegen; zij zien alleen de mailacties zodra de tenant is vrijgegeven.

## Problemen oplossen

| Probleem                               | Oorzaak                                              | Oplossing                                                     |
| -------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------- |
| Verificatiemail niet ontvangen         | Verkeerd adres, of de mail staat in spam             | Controleer het adres en de spam-map; voeg het adres eventueel opnieuw toe |
| Status blijft *In afwachting*          | De bevestigingslink is nog niet gevolgd              | Open de verificatiemail en volg de link                       |
| Gebruikers zien geen mailacties        | Geen geverifieerde afzender, of tenant niet vrijgegeven | Verifieer een afzender; de acties verschijnen na vrijgave  |
| Mail komt niet aan bij ontvangers      | De afzender is nog niet geverifieerd                 | Rond eerst de verificatie af voordat je verstuurt             |
