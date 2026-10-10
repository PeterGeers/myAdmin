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

---

## Runbook: je mail-domein laten certificeren (onboarding)

> Deze sectie beschrijft het **onboardingproces** waarmee je tenant wordt vrijgegeven om te mailen vanaf een **eigen domein** (bijvoorbeeld `noreply@jouwclub.nl`). Dit is een **begeleid, eenmalig** proces — geen zelfbedieningsknop in de applicatie. Je doet het samen met de beheerder (operator) van het platform; jij zet de DNS-records klaar, de operator doet de kant aan de verzendservice en legt de certificering vast.

!!! info
Het verschil met [een afzender toevoegen](#een-afzender-toevoegen-en-verifieren) hierboven: dáár verifieer je één **adres**; hier certificeer je een heel **domein**. Met een gecertificeerd domein verstuurt de Ledenadministratie vanaf `noreply@<jouw-domein>` — een vast, generiek afzenderadres per tenant.

### De afzender die je krijgt

Als je domein is gecertificeerd, gaat elke ledenmail uit vanaf:

- **Van (From):** `noreply@<jouw-domein>` — een vast, generiek adres per tenant (niet instelbaar per gebruiker).
- **Antwoord naar (Reply-To):** het e-mailadres van de ingelogde gebruiker die de mail verstuurt, zodat antwoorden bij de juiste persoon terechtkomen.

!!! info
Het lokale deel (`noreply`) ligt standaard vast. Een afwijkend lokaal deel (bijvoorbeeld `info`) is alleen mogelijk als dat bij de onboarding is afgesproken en vastgelegd.

### Stap 1 — Wat jij aanlevert

Geef aan de operator door:

1. Het **maildomein** dat je wilt gebruiken (bijvoorbeeld `jouwclub.nl`). Dit moet een domein zijn dat je zelf beheert en waarvan je de **DNS kunt aanpassen**.
2. Eventueel een afwijkend **lokaal deel** van de afzender (standaard `noreply`).

### Stap 2 — De operator maakt de domein-identiteit aan

De operator registreert jouw domein als **verzendidentiteit** bij de mailservice (SES). Dat levert een set **DNS-records** op die jij vervolgens aan je domein toevoegt — dit is wat bewijst dat je het domein echt beheert.

### Stap 3 — De DNS-records toevoegen (jouw kant)

Voeg bij je domeinregistrar (of DNS-beheerder) de records toe die de operator je aanlevert:

| Record            | Doel                                                                                     |
| ----------------- | ---------------------------------------------------------------------------------------- |
| **DKIM** (3× CNAME) | Ondertekent je uitgaande mail, zodat ontvangers kunnen controleren dat de mail echt van jouw domein komt. De mailservice levert meestal **drie** CNAME-records aan. |
| **SPF** (TXT)     | Vermeldt welke servers namens je domein mogen verzenden. Neem de door de operator aangeleverde `include` op in je bestaande SPF-record (voeg er geen tweede SPF-record bij). |
| **MAIL FROM** (optioneel, MX + TXT) | Alleen als de operator een eigen "MAIL FROM"-subdomein instelt; voeg dan ook die records toe. |

!!! warning
Voeg **geen tweede SPF-record** toe. Een domein hoort precies één SPF-TXT-record te hebben; staat er al een, vul die dan aan met de aangeleverde `include` in plaats van een nieuwe toe te voegen. Twee SPF-records maken je mail juist onbetrouwbaar.

!!! tip
DNS-wijzigingen kunnen even duren voordat ze overal zichtbaar zijn (van enkele minuten tot soms uren). Heb geduld voordat je de verificatie als mislukt beschouwt.

### Stap 4 — Bevestigen dat het domein geverifieerd is

Zodra de DNS-records live zijn, controleert de mailservice ze automatisch. De operator bevestigt dat de domein-identiteit de status **geverifieerd voor verzenden** heeft (`VerifiedForSendingStatus`). Pas dán is het domein bruikbaar als afzender.

!!! info
Naast de domeinverificatie geldt de account-brede randvoorwaarde dat verzenden is ingeschakeld (uit de "sandbox"). De operator bewaakt dat als operationele voorwaarde; het is geen stap die jij per verzending doet.

### Stap 5 — De certificering vastleggen (`mail_certified`)

Als laatste legt de operator de certificering vast als **tenantparameter**:

| Parameter          | Waarde / betekenis                                                       |
| ------------------ | ------------------------------------------------------------------------ |
| `mail_domain`      | Jouw gecertificeerde domein (bijvoorbeeld `jouwclub.nl`)                 |
| `mail_local_part`  | Het lokale deel van de afzender; standaard `noreply`                     |
| `mail_certified`   | `true` zodra het domein geverifieerd is — dit is de schakelaar waar de verzending op afgaat |
| `mail_enabled`     | `true` om de mailacties voor de tenant vrij te geven                      |

Deze parameters worden bij de onboarding ingevoerd en **doorgezet** (geprojecteerd) naar de verzendomgeving, net als de overige tenantinstellingen. De verzending leest `mail_certified` vlak vóór het versturen: staat die niet op `true`, dan wordt er niet verstuurd.

!!! warning
`mail_certified` is een **vastgelegde** stand, geen live meting. Loopt de certificering van het domein later af (bijvoorbeeld doordat DNS-records worden verwijderd), dan moet de certificering opnieuw worden gecontroleerd en vastgelegd. Haal de DKIM/SPF-records dus niet weg zolang je blijft mailen.

### Als je tenant (nog) niet is gecertificeerd

Zolang `mail_certified` niet op `true` staat, geldt de **fail-closed** regel:

- De verzending wordt **niet** uitgevoerd. Er is **geen** vervangende afzender — nooit een vreemd of platformdomein.
- De gebruiker krijgt een duidelijke, bruikbare melding: *"de mail van je tenant is niet gecertificeerd — neem contact op met je beheerder."*

!!! info
Dit is bewust: liever een duidelijke blokkade met een actie dan een stille mislukking of een mail die vanaf een verkeerd domein de deur uitgaat. Zie ook [Verzenden & bezorging](../members/delivery.md) en [Mailstatus](../members/mail-status.md).

!!! info
Deze certificering hoort bij je **tenantgegevens**. Zie [Instellingen](tenant-settings.md) voor de overige tenantinstellingen; het maildomein en de certificering worden bij de onboarding ingevoerd en bij je tenant bewaard.
