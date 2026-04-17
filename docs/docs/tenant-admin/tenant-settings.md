# Instellingen

> Beheer je organisatie via 6 overzichtelijke tabbladen.

## Overzicht

Het Tenant Beheer dashboard is opgebouwd uit 6 tabbladen. Welke tabbladen je ziet hangt af van je modules en rol.

| Tabblad     | Inhoud                                                   | Zichtbaar voor     |
| ----------- | -------------------------------------------------------- | ------------------ |
| Gebruikers  | Gebruikers toevoegen, rollen toewijzen                   | Tenant Admin       |
| Financieel  | Rekeningschema + Belastingtarieven                       | Tenant Admin (FIN) |
| Opslag      | Opslagprovider kiezen, Google Drive credentials & mappen | Tenant Admin       |
| Sjablonen   | Rapportagesjablonen uploaden, bewerken en goedkeuren     | Tenant Admin       |
| Tenantinfo  | Bedrijfsgegevens, contactinfo, bankgegevens + E-maillog  | Tenant Admin       |
| Geavanceerd | Ruwe parameters tabel                                    | Alleen SysAdmin    |

## Financieel tabblad

Het Financieel tabblad (alleen zichtbaar als de FIN-module actief is) bevat twee secties:

### Rekeningschema

Alle grootboekrekeningen voor je administratie. Klik op een rij om te bewerken.

- **Exporteren** — Download als Excel
- **Importeren** — Upload een Excel-bestand
- **Toevoegen** — Nieuwe rekening aanmaken
- **Parameters** — Per rekening kun je parameters instellen (bijv. BTW saldering, jaarafsluiting doel)

!!! info
Rekeningen die al in transacties worden gebruikt, kunnen niet worden verwijderd.

### Belastingtarieven

Beheer BTW-tarieven en andere belastingtarieven. Klik op een rij om te bewerken. Systeemtarieven (bron: system) kunnen alleen door de SysAdmin worden gewijzigd.

## Opslag tabblad

Configureer waar je bestanden worden opgeslagen.

### Stap 1: Provider kiezen

Kies je opslagprovider:

- **Google Drive** — OAuth-authenticatie + mappenstructuur
- **S3 Shared Bucket** — Gedeelde AWS S3 bucket (platformniveau)
- **S3 Tenant Bucket** — Eigen AWS S3 bucket per tenant

### Stap 2: Provider configureren

**Google Drive:**

1. Upload je credentials JSON-bestand, of start de OAuth-flow
2. Controleer de verbinding met **Test Connection**
3. Vul de Root Folder ID in
4. Bekijk de geconfigureerde mappen (facturen, sjablonen, rapporten)

## Sjablonen tabblad

Sjablonen bepalen hoe factuurverwerking en rapportages eruitzien. Op dit tabblad kun je:

- **Standaardsjabloon downloaden** — Download het ingebouwde sjabloon als startpunt voor aanpassingen
- **Sjabloon uploaden** — Upload een eigen HTML-sjabloon
- **Sjabloon bewerken** — Laad een bestaand sjabloon, bewerk het en upload opnieuw
- **Sjabloon verwijderen** — Verwijder je tenant-specifieke sjabloon en val terug op het standaardsjabloon
- **Valideren en goedkeuren** — Controleer op fouten en activeer het sjabloon

Bij validatiefouten kun je **AI Help** gebruiken voor suggesties.

Zie [Sjabloonbeheer](template-management.md) voor een uitgebreide handleiding.

## Tenantinfo tabblad

Beheer je bedrijfsgegevens in de volgende secties:

- **Bedrijfsinfo** — Administratiecode, weergavenaam, status
- **Contact** — E-mail en telefoonnummer
- **Adres** — Straat, stad, postcode, land
- **Bankgegevens** — Rekeningnummer en banknaam
- **E-maillog** — Overzicht van verzonden e-mails (uitnodigingen, wachtwoord resets)

## Problemen oplossen

| Probleem                            | Oorzaak                                | Oplossing                                     |
| ----------------------------------- | -------------------------------------- | --------------------------------------------- |
| "Tenant admin access required"      | Je hebt niet de Tenant_Admin rol       | Neem contact op met je SysAdmin               |
| Financieel tabblad niet zichtbaar   | FIN-module niet ingeschakeld           | Vraag de SysAdmin om FIN in te schakelen      |
| Geavanceerd tabblad niet zichtbaar  | Je bent geen SysAdmin                  | Alleen SysAdmin ziet dit tabblad              |
| Google Drive verbinding mislukt     | Credentials verlopen of ongeldig       | Upload nieuwe credentials of start OAuth flow |
| Rekening kan niet verwijderd worden | Rekening wordt gebruikt in transacties | De rekening is in gebruik                     |
