# GitHub Discussions Pilot — Context Notes

> Aanvullende context bij deze spec. **Geen code, geen requirements** — dit legt de
> GitHub-bevindingen en beslissingen vast zodat ze niet verloren gaan. De eigenlijke
> module (zie `requirements.md`) wordt in myAdmin gebouwd; GitHub Discussions is een
> *optioneel, los pilot-spoor* voor de kleine groep gebruikers die wél een GitHub-account
> heeft.

## Waarom twee sporen

De gewenste Support/Q&A-functie heeft gebruikers die **grotendeels geen GitHub-account
hebben** en zelf vragen/antwoorden moeten kunnen plaatsen. GitHub (Issues/Discussions)
vereist per deelnemer een account + toegang, dus GitHub is **geen geschikt kanaal voor de
brede gebruikersgroep**. Daarom:

- **Spoor 1 — In-app Support & Feedback-module (hoofdoplossing).** In myAdmin, op de
  SAM/Members-plane, tenant-geïsoleerd. Bereikt álle ingelogde gebruikers zonder nieuw
  account. Zie `requirements.md`.
- **Spoor 2 — GitHub Discussions-pilot (optioneel, klein).** Alleen voor uitgenodigde
  gebruikers die een GitHub-account hebben, binnen de `H-DCN`-organisatie. Snel op te
  zetten, maar beperkt bereik.

## GitHub-organisatie (bevestigd)

- Org: **H-DCN** — https://github.com/H-DCN — org-id `344838383`.
- Ingelogde `gh`-gebruiker: **PeterGeers**, rol in de org: **admin** (active).

## Wat `gh` / de GitHub-API kan aanmaken (automatiseerbaar)

Mits de juiste token-scopes aanwezig zijn:

- Repository aanmaken onder de org (`gh repo create H-DCN/support --private`).
- Labels, issues en issue-templates.
- **Discussions aanzetten + categorieën aanmaken + discussions posten** via de GraphQL-API
  (`gh api graphql`).
- Teams aanmaken en leden uitnodigen (org-API).
- Bestanden committen (templates, README/handleiding).

## Blokkade: ontbrekende token-scopes

De huidige `gh`-token-scopes zijn: `gist`, `read:org`, `repo`, `workflow`.

Dat is **onvoldoende** voor het pilot-spoor. Nodig:

| Actie | Vereiste scope | Aanwezig? |
| --- | --- | --- |
| Private repo onder org aanmaken | `repo` | ✅ |
| Labels / issues / bestanden committen | `repo` | ✅ |
| Org-teams aanmaken + leden uitnodigen | `admin:org` | ❌ (alleen `read:org`) |
| Discussions-categorieën beheren / posten | `write:discussion` | ❌ |

**Herautoriseren** (door de eigenaar uit te voeren; wijzigt auth, dus niet agent-actie):

```bash
gh auth refresh -h github.com -s admin:org -s write:discussion
```

Let op: ook ná het verruimen van de scopes kan **Discussions aanzetten op repo-niveau** een
UI-afhankelijke stap zijn; categorieën en posts zijn daarna wél via de GraphQL-API te doen.

## Voorgestelde pilot-opzet (zodra scopes verruimd zijn)

1. Repo `H-DCN/support` (**private**).
2. Discussions aan; categorieën: **Q&A** (vraag/antwoord, geaccepteerd antwoord) en
   **Ideeën** (verbeteringen, met stemmen); optioneel **Hoe werkt het** en
   **Aankondigingen**.
3. Discussion-templates: "Stel een vraag" en "Doe een verbetervoorstel" — met dropdown voor
   **functioneel gebied** en een veld voor **screenshots**.
4. Team `members` met **Write**-rechten; leden uitnodigen (hebben GitHub-account nodig).
5. Een vastgepinde welkomst-/handleidingspost (NL + EN).

## Afbakening

- Dit pilot-spoor is **niet** de hoofdoplossing en vervangt de in-app module niet.
- Scope-verruiming en org-/discussion-acties zijn **eigenaar-acties** (auth-wijziging);
  de agent voert die niet zelf uit zonder expliciete opdracht.

## Kosten (GitHub) + "blijf in het gratis plan"-regel

**Harde randvoorwaarde: deze pilot blijft op het GitHub Free-plan (€0). Geen betaalde
upgrade (Team/Enterprise) zonder expliciete toestemming van de eigenaar.**

### Actuele GitHub-prijzen (geverifieerd okt. 2026)

| Plan | Prijs | Nodig voor pilot? |
| --- | --- | --- |
| **Free** (org) | **€0 / $0** | ✅ Onbeperkt private repos, onbeperkt collaborators, Discussions, Issues, teams |
| **Team** | ~$4 per gebruiker/mnd | ❌ alleen nodig voor fijnmazige rechten (bv. read-only op private repo) |
| **Enterprise** | vanaf ~$21 per gebruiker/mnd | ❌ niet nodig |

> De $4 / $21 staan op GitHub's prijspagina als tarief "voor de eerste 12 maanden"; het
> tarief daarna wordt niet publiek vermeld. Bronnen:
> [github.com/pricing](https://github.com/pricing),
> [GitHub docs — plans](https://docs.github.com/get-started/learning-about-github/githubs-products).
> Prijsinfo herschreven t.b.v. licentie-compliance; tarieven kunnen wijzigen.

### De enige Free-valkuil: read-only toegang

Op een **private** repo in Free krijgen collaborators standaard **Write**. **Read-only**
(alleen lezen) voor specifieke gebruikers bestaat pas vanaf **Team/Enterprise** (betaald).
Bron: [GitHub community discussion #160042](https://github.com/orgs/community/discussions/160042)
(herschreven t.b.v. compliance).

Voor een Q&A-pilot is dat meestal géén bezwaar: deelnemers moeten juist kunnen posten en
antwoorden, dus Write is gewenst.

### Twee Free-conforme opties (kies er één)

| Variant | Zichtbaarheid | Wie kan lezen | Wie kan schrijven | Kosten | Let op |
| --- | --- | --- | --- | --- | --- |
| **A. Private + Write-deelnemers** (aanbevolen) | Private | Alleen uitgenodigde teamleden | Alle uitgenodigde teamleden | €0 | Geen read-only-rol; iedereen die mee mag doen kan schrijven. Inhoud blijft besloten. |
| **B. Public + read-only publiek** | Public | Iedereen (ook zonder account) | Alleen uitgenodigde teamleden | €0 | Read-only "gratis" via publieke leesbaarheid — **maar de inhoud is openbaar zichtbaar**. Niet gebruiken als vragen vertrouwelijke/leden-specifieke info bevatten. |

**Aanbeveling:** **Variant A** (private, deelnemers met Write). Dit houdt de inhoud besloten
én blijft gratis, passend bij een Q&A waar deelname = kunnen posten. Variant B alleen als
openbare leesbaarheid gewenst is en er geen vertrouwelijke inhoud in staat.

### Blijf-gratis-regels voor de uitvoering

1. Repo onder `H-DCN` aanmaken als **private** (Variant A) — nooit automatisch een
   betaald plan activeren.
2. **Geen** `gh`/API-actie die een Team/Enterprise-upgrade of betaalde seats triggert.
3. Deelnemers toevoegen via een **team met Write** (Free-conform) — geen poging tot
   read-only rollen op een private repo (dat zou Team vereisen).
4. Bijlagen/screenshots: binnen de normale repo-limieten houden (een paar screenshots is
   verwaarloosbaar) — geen betaalde opslaguitbreiding.
5. De echte drempel blijft niet-geldelijk: **elke deelnemer heeft een GitHub-account nodig**.
