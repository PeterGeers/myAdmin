# Tenant beheer

> Tenants aanmaken, configureren, modules toewijzen en de eerste beheerder uitnodigen.

## Overzicht

Als SysAdmin beheer je alle tenants (organisaties) op het platform. Je maakt nieuwe tenants aan, wijst modules toe, en nodigt de eerste Tenant Admin uit die vervolgens het beheer van de organisatie overneemt.

## Wat je nodig hebt

- `SysAdmin` rol in AWS Cognito
- Toegang tot het SysAdmin-paneel

## Stap voor stap

### Een nieuwe tenant aanmaken

1. Ga naar het **SysAdmin**-paneel
2. Klik op **Nieuwe tenant aanmaken**
3. Vul de basisgegevens in:

| Veld              | Beschrijving                                     | Verplicht |
| ----------------- | ------------------------------------------------ | --------- |
| Administratienaam | Unieke naam voor de tenant (bijv. "MijnBedrijf") | ✅        |
| Weergavenaam      | Naam zoals getoond in de interface               | ✅        |
| Status            | Actief of inactief                               | ✅        |

4. Klik op **Aanmaken**

### Modules toewijzen

Na het aanmaken van een tenant wijs je modules toe:

1. Open de tenant in het SysAdmin-paneel
2. Ga naar het tabblad **Modules**
3. Schakel de gewenste modules in:

| Module         | Wat het biedt                                 |
| -------------- | --------------------------------------------- |
| **Financieel** | Bankzaken, facturen, rapportages, belastingen |
| **STR**        | Kortetermijnverhuur, boekingen, prijzen       |

4. Klik op **Opslaan**

!!! info
Modules bepalen welke functionaliteit beschikbaar is voor de tenant. Gebruikers zien alleen de modules die zijn ingeschakeld.

### Eerste beheerder uitnodigen

Na het aanmaken en configureren van de tenant nodig je de eerste Tenant Admin uit:

1. De tenant wordt geprovisioneerd in AWS Cognito
2. De eerste gebruiker ontvangt een welkomstmail met inloggegevens
3. Deze gebruiker krijgt de `Tenant_Admin` rol
4. De Tenant Admin kan vervolgens zelf gebruikers toevoegen

### Tenant bewerken

1. Open de tenant in het SysAdmin-paneel
2. Pas de gewenste velden aan
3. Klik op **Opslaan**

### Tenant verwijderen

1. Open de tenant in het SysAdmin-paneel
2. Klik op **Verwijderen**
3. Bevestig de actie

!!! danger
Verwijderen is een soft delete — de tenant wordt gemarkeerd als "deleted" maar de data blijft in de database. Dit kan niet ongedaan worden gemaakt via de interface.

## Provisioning

Bij het aanmaken of herprovisioneren van een tenant:

- Cognito-gebruikersgroepen worden aangemaakt
- De eerste beheerder wordt uitgenodigd per e-mail
- Een welkomstmail wordt verstuurd met inloggegevens
- De administratienaam wordt toegevoegd aan het Cognito-profiel van de gebruiker

### Herprovisioneren

Als er iets mis is gegaan bij de initiële setup kun je een tenant herprovisioneren:

1. Open de tenant
2. Klik op **Herprovisioneren**
3. Het systeem voert de provisioningstappen opnieuw uit

## Rollenbeheer

Als SysAdmin kun je ook rollen (Cognito-groepen) beheren:

- **Rollen bekijken** — Alle beschikbare rollen met het aantal gebruikers
- **Rol aanmaken** — Nieuwe rol toevoegen
- **Rol verwijderen** — Rol verwijderen (alleen als er geen gebruikers aan gekoppeld zijn)

## Problemen oplossen

| Probleem                    | Oorzaak                         | Oplossing                                  |
| --------------------------- | ------------------------------- | ------------------------------------------ |
| Tenant aanmaken mislukt     | Naam al in gebruik              | Kies een unieke administratienaam          |
| Modules niet zichtbaar      | Modules niet toegewezen         | Wijs modules toe via het SysAdmin-paneel   |
| Gebruiker kan niet inloggen | Provisioning niet voltooid      | Herprovisioneer de tenant                  |
| Rol verwijderen mislukt     | Gebruikers gekoppeld aan de rol | Verwijder eerst alle gebruikers uit de rol |
