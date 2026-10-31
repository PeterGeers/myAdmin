# STR Overview

**Status**: Active
**Purpose**: Short-term-rental (STR) booking import, revenue/pricing, country reporting, and
tourist-tax declarations.

## Specs in this area

| Spec | Status | Description | Link |
| --- | --- | --- | --- |
| stripe-tenant-credentials | active | Per-tenant Stripe credential handling for STR. | [stripe-tenant-credentials](stripe-tenant-credentials) |
| Reports | active | STR reporting specs. | [Reports](Reports) |
| Country_Report | active | Per-country STR reporting. | [Country_Report](Country_Report) |
| STR Invoice generator | active | STR invoice generation. | [STR Invoice generator](STR%20Invoice%20generator) |
| Haarlemmermeer STR Toeristenbelasting | active | Tourist-tax declaration for the Haarlemmermeer municipality. | [Haarlemmermeer STR Toeristenbelasting](Haarlemmermeer%20STR%20Toeristenbelasting) |
| Prijsmodel en AI integratie | active | Pricing model and AI integration for STR. | [Prijsmodel en AI integratie](Prijsmodel%20en%20AI%20integratie) |
| Import STR | active | STR booking import. | [Import STR](Import%20STR) |
| import-df-direct | active | Direct dataframe import path for STR. | [import-df-direct](import-df-direct) |
| airbnb-export-format-update | active | Airbnb export/CSV format handling. | [airbnb-export-format-update](airbnb-export-format-update) |

## Conventions

Completed specs move to `_archive/` and are marked `"status": "done"` in their `.config.kiro`.
Active specs sit directly in this folder. See the root
[`.kiro/specs/README.md`](../README.md) for the overall model.
