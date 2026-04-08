# Gebruikersbeheer

> Gebruikers toevoegen aan je organisatie en rollen toewijzen.

## Overzicht

Als Tenant Admin beheer je de gebruikers van je organisatie. Je kunt nieuwe gebruikers aanmaken, rollen toewijzen en verwijderen, en gebruikers deactiveren.

## Wat je nodig hebt

- `Tenant_Admin` rol
- Een geselecteerde tenant/administratie

## Stap voor stap

### Gebruikers bekijken

1. Ga naar **Tenant Beheer** → **Gebruikers**
2. Je ziet een lijst van alle gebruikers met toegang tot je tenant

Per gebruiker zie je:

| Kolom          | Beschrijving                                     |
| -------------- | ------------------------------------------------ |
| Gebruikersnaam | Unieke naam in het systeem                       |
| E-mail         | E-mailadres van de gebruiker                     |
| Rollen         | Toegewezen rollen (bijv. Finance_CRUD, STR_Read) |
| Status         | Actief, inactief of wachtend op bevestiging      |

### Nieuwe gebruiker aanmaken

1. Klik op **Gebruiker toevoegen**
2. Vul de gegevens in:

| Veld        | Beschrijving                   | Verplicht |
| ----------- | ------------------------------ | --------- |
| E-mailadres | E-mail van de nieuwe gebruiker | ✅        |
| Voornaam    | Voornaam                       | ✅        |
| Achternaam  | Achternaam                     | ✅        |

3. Wijs rollen toe (zie hieronder)
4. Klik op **Aanmaken**

De gebruiker ontvangt een e-mail met inloggegevens en moet bij de eerste login een wachtwoord instellen.

### Rollen toewijzen

1. Klik op een gebruiker in de lijst
2. Klik op **Rol toewijzen**
3. Selecteer de gewenste rol uit de beschikbare rollen
4. Klik op **Toewijzen**

Beschikbare rollen zijn afhankelijk van de ingeschakelde modules:

| Module ingeschakeld | Beschikbare rollen                               |
| ------------------- | ------------------------------------------------ |
| Financieel          | `Finance_Read`, `Finance_CRUD`, `Finance_Export` |
| STR                 | `STR_Read`, `STR_CRUD`, `STR_Export`             |
| Altijd              | `Tenant_Admin`                                   |

### Rollen verwijderen

1. Klik op een gebruiker in de lijst
2. Klik op het verwijdericoon naast de rol die je wilt verwijderen
3. Bevestig de actie

### Gebruiker verwijderen

1. Klik op een gebruiker in de lijst
2. Klik op **Verwijderen**
3. Bevestig de actie

!!! warning
Als de gebruiker toegang heeft tot meerdere tenants, wordt alleen de toegang tot jouw tenant verwijderd. De gebruiker behoudt toegang tot andere tenants. Alleen als de gebruiker uitsluitend aan jouw tenant is gekoppeld, wordt het account volledig verwijderd.

### Uitnodiging opnieuw versturen

Als een gebruiker de uitnodigingsmail niet heeft ontvangen of het tijdelijke wachtwoord is verlopen:

1. Klik op de gebruiker in de lijst
2. Klik op **Uitnodiging opnieuw versturen**
3. Er wordt een nieuw tijdelijk wachtwoord gegenereerd en per e-mail verstuurd

!!! info
Als de e-mail niet kan worden verstuurd, wordt het tijdelijke wachtwoord getoond zodat je het handmatig kunt delen.

## E-maillogboek

Alle e-mails die vanuit het systeem worden verstuurd (uitnodigingen, wachtwoord-resets, tenant-toevoegingen) worden bijgehouden in het e-maillogboek. Als Tenant Admin zie je alleen de e-mails voor jouw tenant.

Het logboek toont:

| Kolom     | Beschrijving                                       |
| --------- | -------------------------------------------------- |
| Ontvanger | E-mailadres van de ontvanger                       |
| Type      | Soort e-mail (uitnodiging, wachtwoord-reset, etc.) |
| Status    | Verzonden, afgeleverd, gebounced of klacht         |
| Datum     | Wanneer de e-mail is verstuurd                     |

## Tips

!!! tip
Wijs gebruikers alleen de rollen toe die ze nodig hebben. Een medewerker die alleen rapporten bekijkt heeft genoeg aan `Finance_Read` — geen `Finance_CRUD` nodig.

- Elke gebruiker kan meerdere rollen hebben
- Een gebruiker kan toegang hebben tot meerdere tenants (als de SysAdmin dit heeft geconfigureerd)
- Alle wijzigingen aan gebruikers worden vastgelegd in het auditlogboek

## Problemen oplossen

| Probleem                       | Oorzaak                                 | Oplossing                                                                                              |
| ------------------------------ | --------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| "Tenant admin access required" | Je hebt niet de Tenant_Admin rol        | Neem contact op met je SysAdmin                                                                        |
| Gebruiker ziet geen modules    | Geen rollen toegewezen                  | Wijs de juiste rollen toe                                                                              |
| Rol niet beschikbaar           | Module niet ingeschakeld voor je tenant | Neem contact op met je SysAdmin om de module in te schakelen                                           |
| Gebruiker kan niet inloggen    | Account niet geactiveerd                | Controleer de gebruikersstatus; gebruik "Uitnodiging opnieuw versturen" als het wachtwoord is verlopen |
