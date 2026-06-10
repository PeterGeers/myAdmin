Als je een AI wilt gebruiken om de security-aanpak van een applicatie te beoordelen, werkt een prompt het beste als je de AI laat denken als een security architect, threat modeler én pentester.

# Een sterke algemene prompt:

Analyseer de security-architectuur van deze applicatie alsof je een senior security architect bent.

Geef een beoordeling van:

Authenticatie
Autorisatie
Multi-tenant security
API security
Data security (at rest en in transit)
Secrets management
Logging en auditing
Input validatie
OWASP Top 10 risico's
Infrastructure security
Compliance (GDPR, SOC2, ISO27001)

Identificeer:

Kritieke kwetsbaarheden
Mogelijke aanvalsscenario's
Ontbrekende controles
Risico-impact
Prioriteit van mitigaties

Maak een threat model volgens STRIDE.

Geef de uitkomst in een tabel met:
Risico | Impact | Kans | Aanbeveling | Prioriteit.

Hier is de architectuur:

[beschrijving]

# Voor jouw SaaS-platform (ledenadministratie/webshop/multi-tenant) zou ik nog specifieker gaan:

Analyseer deze multi-tenant SaaS-oplossing op security.

Controleer specifiek:

Tenant-isolatie
Cross-tenant datalekken
IAM-model
RBAC/ABAC
DynamoDB partition key ontwerp
API Gateway beveiliging
AWS Cognito authenticatie
JWT-validatie
S3 beveiliging
SES e-mailbeveiliging
Payment security
Rate limiting
DDoS bescherming
Audit logging
Back-up en disaster recovery

Geef voor elk onderdeel:

Risico's
Mogelijke exploits
Severity (Critical/High/Medium/Low)
Concrete AWS best practices
Implementatievoorbeelden

# Nog krachtiger is om de AI als een aanvaller te laten redeneren:

Gedraag je als een red-team security consultant.

Zoek naar manieren waarop een kwaadwillende gebruiker:

Data van andere tenants kan lezen
Rechten kan escaleren
Betalingen kan manipuleren
Tickets kan vervalsen
DynamoDB queries kan misbruiken
JWT tokens kan vervalsen
Business rules kan omzeilen

Beschrijf stap voor stap hoe de aanval werkt en hoe deze voorkomen kan worden.

Dat laatste levert vaak de meest waardevolle inzichten op omdat je dan niet alleen een checklist krijgt, maar echte aanvalspaden voor jouw specifieke applicatie.