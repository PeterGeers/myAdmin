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

!!! danger
Het verwijderen van een gebruiker is definitief. De gebruiker verliest alle toegang tot het platform.

## Tips

!!! tip
Wijs gebruikers alleen de rollen toe die ze nodig hebben. Een medewerker die alleen rapporten bekijkt heeft genoeg aan `Finance_Read` — geen `Finance_CRUD` nodig.

- Elke gebruiker kan meerdere rollen hebben
- Een gebruiker kan toegang hebben tot meerdere tenants (als de SysAdmin dit heeft geconfigureerd)
- Alle wijzigingen aan gebruikers worden vastgelegd in het auditlogboek

## Problemen oplossen

| Probleem                       | Oorzaak                                 | Oplossing                                                    |
| ------------------------------ | --------------------------------------- | ------------------------------------------------------------ |
| "Tenant admin access required" | Je hebt niet de Tenant_Admin rol        | Neem contact op met je SysAdmin                              |
| Gebruiker ziet geen modules    | Geen rollen toegewezen                  | Wijs de juiste rollen toe                                    |
| Rol niet beschikbaar           | Module niet ingeschakeld voor je tenant | Neem contact op met je SysAdmin om de module in te schakelen |
| Gebruiker kan niet inloggen    | Account niet geactiveerd                | Controleer de gebruikersstatus                               |
