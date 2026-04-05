# Tenant Beheer

> Instellingen, gebruikers en audit logging voor je organisatie.

## Overzicht

Als Tenant Admin beheer je je eigen organisatie binnen myAdmin. Je beheert gebruikers, configureert instellingen en houdt activiteiten bij via het auditlogboek. Je hebt geen toegang tot andere tenants of platforminstellingen — dat is voorbehouden aan de [SysAdmin](../admin/index.md).

!!! info
Je bent Tenant Admin geworden doordat de SysAdmin je heeft uitgenodigd als eerste beheerder van je organisatie. Vanaf dat moment kun je zelf gebruikers toevoegen en rollen toewijzen.

## Wat kun je hier doen?

| Taak                                   | Beschrijving                                             |
| -------------------------------------- | -------------------------------------------------------- |
| [Instellingen](tenant-settings.md)     | Tenant configuratie, sjablonen en rekeningschema beheren |
| [Gebruikersbeheer](user-management.md) | Gebruikers toevoegen, rollen toewijzen en verwijderen    |
| [Audit logging](audit-logging.md)      | Activiteiten bijhouden en compliance rapporten           |

## Jouw rol vs SysAdmin

|                  | Tenant Admin                            | SysAdmin                           |
| ---------------- | --------------------------------------- | ---------------------------------- |
| **Scope**        | Je eigen organisatie                    | Het hele platform                  |
| **Gebruikers**   | Toevoegen, rollen toewijzen/verwijderen | Eerste Tenant Admin uitnodigen     |
| **Instellingen** | Tenant configuratie, sjablonen          | Modules toewijzen, tenant aanmaken |
| **Data**         | Alleen je eigen tenant-data             | Alle tenants                       |

## Beschikbare rollen om toe te wijzen

Als Tenant Admin kun je de volgende rollen toewijzen aan gebruikers in je organisatie:

| Rol              | Wat de gebruiker kan                                           |
| ---------------- | -------------------------------------------------------------- |
| `Tenant_Admin`   | Alles wat jij kunt (gebruikers beheren, instellingen wijzigen) |
| `Finance_Read`   | Financiële rapporten bekijken                                  |
| `Finance_CRUD`   | Financiële data bewerken (importeren, transacties aanpassen)   |
| `Finance_Export` | Financiële data exporteren (Excel, CSV)                        |
| `STR_Read`       | STR-rapporten bekijken                                         |
| `STR_CRUD`       | STR-data bewerken (boekingen importeren)                       |
| `STR_Export`     | STR-data exporteren                                            |

!!! warning
Welke rollen beschikbaar zijn hangt af van de modules die de SysAdmin voor je tenant heeft ingeschakeld. Als de STR-module niet is ingeschakeld, zijn de STR-rollen niet beschikbaar.

## Stap voor stap: Eerste keer als Tenant Admin

1. **Log in** met de gegevens die je per e-mail hebt ontvangen
2. **Wijzig je wachtwoord** bij de eerste login
3. **Bekijk de instellingen** via [Instellingen](tenant-settings.md)
4. **Voeg gebruikers toe** via [Gebruikersbeheer](user-management.md)
5. **Wijs rollen toe** zodat gebruikers de juiste modules kunnen gebruiken
