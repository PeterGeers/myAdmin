# Docker deployment

> Docker-containers beheren, starten, stoppen en bijwerken.

## Overzicht

myAdmin draait in Docker-containers: een MySQL database en een Flask backend. Deze pagina beschrijft hoe je de containers beheert.

## Architectuur

| Container   | Image        | Poort | Resources           |
| ----------- | ------------ | ----- | ------------------- |
| **mysql**   | MySQL 8.0    | 3306  | 2 GB RAM, 1 CPU     |
| **backend** | Flask/Python | 5000  | 512 MB RAM, 1.5 CPU |

De MySQL-data wordt opgeslagen in `./mysql_data/` op de host, zodat data behouden blijft bij het herstarten van containers.

## Stap voor stap

### Alle services starten

```bash
docker-compose up -d
```

### Alle services stoppen

```bash
docker-compose down
```

### Logs bekijken

```bash
docker-compose logs -f backend    # Backend logs
docker-compose logs -f mysql      # Database logs
```

### Opnieuw bouwen na codewijzigingen

```bash
docker-compose up -d --build
```

### Status controleren

```bash
docker-compose ps
```

## Health check

De backend heeft een ingebouwde health check:

- **Endpoint**: `http://localhost:5000/api/health`
- **Interval**: Elke 30 seconden
- **Timeout**: 10 seconden
- **Retries**: 3 pogingen
- **Start periode**: 40 seconden wachttijd bij opstarten

## Omgevingsvariabelen

De backend leest configuratie uit `backend/.env`. Belangrijke variabelen:

| Variabele              | Beschrijving                       |
| ---------------------- | ---------------------------------- |
| `DB_HOST`              | Database host (in Docker: `mysql`) |
| `DB_USER`              | Database gebruiker                 |
| `DB_PASSWORD`          | Database wachtwoord                |
| `DB_NAME`              | Database naam                      |
| `TEST_MODE`            | `true` of `false`                  |
| `AWS_REGION`           | AWS regio voor Cognito             |
| `COGNITO_USER_POOL_ID` | AWS Cognito User Pool ID           |

!!! warning
Wijzig `DB_HOST` niet in de Docker-configuratie — deze wordt automatisch overschreven naar `mysql` (de containernaam).

## Volumes

| Volume         | Host pad           | Container pad         | Doel                   |
| -------------- | ------------------ | --------------------- | ---------------------- |
| MySQL data     | `./mysql_data`     | `/var/lib/mysql`      | Database bestanden     |
| Backend code   | `./backend`        | `/app`                | Applicatiecode         |
| Frontend build | `./frontend/build` | `/app/frontend/build` | Statische frontend     |
| Reports        | Configureerbaar    | `/app/reports`        | Gegenereerde rapporten |

## Tips

!!! tip
Gebruik `docker-compose logs -f backend` om real-time te zien wat de backend doet. Dit is handig bij het debuggen van problemen.

- Start altijd MySQL vóór de backend (docker-compose doet dit automatisch via `depends_on`)
- De MySQL-data overleeft container-herstarts dankzij de host directory mapping
- Gebruik `--build` na het wijzigen van Python-dependencies

## Problemen oplossen

| Probleem            | Oorzaak                               | Oplossing                                                          |
| ------------------- | ------------------------------------- | ------------------------------------------------------------------ |
| Backend start niet  | MySQL nog niet klaar                  | Wacht 40 seconden (start_period) of herstart de backend            |
| Poort 5000 bezet    | Andere applicatie op poort 5000       | Stop de andere applicatie of wijzig de poort in docker-compose.yml |
| MySQL data verloren | Volume niet correct gemount           | Controleer of `./mysql_data/` bestaat en schrijfbaar is            |
| Out of memory       | Container overschrijdt geheugenlimiet | Verhoog `mem_limit` in docker-compose.yml                          |
