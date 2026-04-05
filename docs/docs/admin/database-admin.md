# Database administratie

> MySQL beheer, migraties en backups.

## Overzicht

myAdmin gebruikt MySQL 8.0 als database. De database draait in een Docker-container met data opgeslagen op de host. Deze pagina beschrijft veelvoorkomende beheertaken.

## Verbinding maken

### Lokaal via Docker

```bash
docker-compose exec mysql mysql -u peter -p
```

### Lokaal (als MySQL op de host draait)

```bash
mysql -u peter -p -h localhost -P 3306
```

### Railway (productie)

De productiedatabase draait op Railway. Verbinding maken:

1. Ga naar het Railway dashboard → MySQL service
2. Kopieer de verbindingsgegevens (host, poort, gebruiker, wachtwoord)
3. Gebruik een MySQL-client:

```bash
mysql -h <railway-host> -P <railway-port> -u <user> -p <database>
```

!!! info
De backend verbindt automatisch met Railway MySQL via de `RAILWAY_PRIVATE_DOMAIN` omgevingsvariabele. Lokaal valt het systeem terug op `DB_HOST` of `localhost`.

## Belangrijke tabellen

| Tabel                     | Beschrijving                   |
| ------------------------- | ------------------------------ |
| `mutaties`                | Financiële transacties         |
| `bnb`                     | Gerealiseerde STR-boekingen    |
| `bnbplanned`              | Geplande STR-boekingen         |
| `bnbfuture`               | Toekomstige omzet samenvatting |
| `listings`                | Verhuurobjecten                |
| `tenants`                 | Tenant configuratie            |
| `pricing_recommendations` | Prijsaanbevelingen             |
| `pricing_events`          | Evenementen voor prijsopslagen |
| `audit_log`               | Audit trail                    |

### Views

| View          | Beschrijving                                       |
| ------------- | -------------------------------------------------- |
| `vw_mutaties` | Rapportageview met grootboekrekeningen en periodes |

## Deployment-omgevingen

myAdmin draait in twee omgevingen:

| Omgeving                | Database host            | Configuratie                 |
| ----------------------- | ------------------------ | ---------------------------- |
| **Lokaal (Docker)**     | `mysql` (containernaam)  | `docker-compose.yml`         |
| **Productie (Railway)** | `RAILWAY_PRIVATE_DOMAIN` | Railway dashboard variabelen |

De backend bepaalt automatisch de juiste host:

```
Host = DB_HOST → RAILWAY_PRIVATE_DOMAIN → localhost (fallback)
```

## Test- en productiedatabase

Het systeem gebruikt twee databases:

| Modus     | Database                  | Configuratie |
| --------- | ------------------------- | ------------ |
| Productie | `DB_NAME` uit `.env`      | Echte data   |
| Test      | `TEST_DB_NAME` uit `.env` | Testdata     |

De modus wordt bepaald door de `TEST_MODE` variabele in `backend/.env`.

!!! warning
Voer nooit testscripts uit op de productiedatabase. Controleer altijd de `TEST_MODE` instelling voordat je wijzigingen maakt.

## Migraties

Database-migraties worden uitgevoerd via scripts in `backend/scripts/database/`:

```bash
python scripts/database/fix_database_views.py
```

## Backups

### Handmatige backup

```bash
docker-compose exec mysql mysqldump -u peter -p finance > backup_$(date +%Y%m%d).sql
```

### Backup herstellen

```bash
docker-compose exec -T mysql mysql -u peter -p finance < backup_20260401.sql
```

## Tips

!!! tip
Maak altijd een backup voordat je migraties uitvoert of grote wijzigingen maakt aan de database.

- De MySQL-data staat in `./mysql_data/` — maak hier regelmatig een kopie van
- Gebruik `vw_mutaties` voor rapportages in plaats van direct de `mutaties` tabel te bevragen
- De `--lower-case-table-names=2` instelling zorgt voor case-insensitive tabelnamen

## Problemen oplossen

| Probleem            | Oorzaak                     | Oplossing                                                      |
| ------------------- | --------------------------- | -------------------------------------------------------------- |
| Kan niet verbinden  | MySQL container draait niet | Start de containers met `docker-compose up -d`                 |
| Tabel niet gevonden | View niet aangemaakt        | Voer `fix_database_views.py` uit                               |
| Trage queries       | Ontbrekende indexen         | Controleer de indexen op veelgebruikte kolommen                |
| Disk vol            | MySQL data te groot         | Controleer de grootte van `./mysql_data/` en ruim oude data op |
