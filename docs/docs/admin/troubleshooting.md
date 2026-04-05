# Problemen oplossen

> Veelvoorkomende platformproblemen en oplossingen.

## Overzicht

Deze pagina beschrijft veelvoorkomende problemen die je als SysAdmin kunt tegenkomen en hoe je ze oplost.

## Applicatie start niet

| Symptoom                           | Mogelijke oorzaak             | Oplossing                                                          |
| ---------------------------------- | ----------------------------- | ------------------------------------------------------------------ |
| Backend geeft "Connection refused" | MySQL is nog niet klaar       | Wacht 40 seconden na `docker-compose up -d` of herstart de backend |
| "Module not found" fout            | Python-dependencies ontbreken | Voer `docker-compose up -d --build` uit om opnieuw te bouwen       |
| Frontend toont witte pagina        | Build is verouderd            | Bouw de frontend opnieuw met `npm run build` in de frontend-map    |
| Health check faalt                 | Backend crasht bij opstarten  | Bekijk logs met `docker-compose logs backend`                      |

## Database problemen

| Symptoom               | Mogelijke oorzaak             | Oplossing                                                |
| ---------------------- | ----------------------------- | -------------------------------------------------------- |
| "Access denied"        | Verkeerde credentials         | Controleer `DB_USER` en `DB_PASSWORD` in `backend/.env`  |
| "Table doesn't exist"  | Views niet aangemaakt         | Voer `python scripts/database/fix_database_views.py` uit |
| Trage performance      | Grote tabellen zonder indexen | Controleer indexen en overweeg archivering van oude data |
| "Too many connections" | Connection pool uitgeput      | Herstart de backend container                            |

## Authenticatie problemen

| Symptoom                    | Mogelijke oorzaak            | Oplossing                                                   |
| --------------------------- | ---------------------------- | ----------------------------------------------------------- |
| "Invalid token"             | Cognito-configuratie onjuist | Controleer `COGNITO_USER_POOL_ID` en `AWS_REGION` in `.env` |
| Gebruiker kan niet inloggen | Account niet geactiveerd     | Controleer de gebruikersstatus in AWS Cognito Console       |
| "Access denied" op API      | Ontbrekende rol              | Wijs de juiste Cognito-groep toe aan de gebruiker           |
| Token verlopen              | Sessie te lang inactief      | Gebruiker moet opnieuw inloggen                             |

## Google Drive problemen

| Symptoom                      | Mogelijke oorzaak               | Oplossing                                     |
| ----------------------------- | ------------------------------- | --------------------------------------------- |
| "OAuth credentials not found" | Credentials niet geconfigureerd | Configureer Google Drive OAuth voor de tenant |
| Upload mislukt                | Token verlopen                  | Vernieuw de Google Drive OAuth-token          |
| Bestanden niet bereikbaar     | Onvoldoende rechten             | Controleer de Google Drive-machtigingen       |

## Tenant problemen

| Symptoom               | Mogelijke oorzaak           | Oplossing                                                                |
| ---------------------- | --------------------------- | ------------------------------------------------------------------------ |
| Tenant ziet geen data  | Verkeerde administratienaam | Controleer of de administratienaam overeenkomt in Cognito en de database |
| Modules niet zichtbaar | Modules niet toegewezen     | Wijs modules toe via het SysAdmin-paneel                                 |
| Provisioning mislukt   | AWS Cognito API-fout        | Controleer AWS-credentials en probeer opnieuw te provisioneren           |

## Diagnostische commando's

### Container status

```bash
docker-compose ps
docker-compose logs --tail=50 backend
docker-compose logs --tail=50 mysql
```

### Database connectiviteit

```bash
docker-compose exec mysql mysqladmin -u peter -p ping
```

### API health check

```bash
curl http://localhost:5000/api/health
```

### Disk gebruik

```bash
du -sh ./mysql_data/
docker system df
```

## Tips

!!! tip
Bewaar altijd de laatste 50 regels van de backend-logs wanneer je een probleem rapporteert. Dit helpt bij het snel identificeren van de oorzaak.

- Controleer altijd eerst de logs voordat je containers herstart
- De meeste problemen worden veroorzaakt door verkeerde `.env` configuratie
- Bij twijfel: herstart de containers met `docker-compose down && docker-compose up -d`
