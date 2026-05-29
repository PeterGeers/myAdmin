# UBL/XML Invoice Support — Research & Analysis Summary

## Context

This document summarizes the research and discussion around Dutch invoice storage obligations and the potential for UBL/XML invoice support in myAdmin.

## Dutch Invoice Storage Obligations (Bewaarplicht)

### Retention Requirements

- **Standard retention**: 7 years for all invoices and financial records
- **Real estate-related**: 10 years
- Records must remain **readable and unaltered** throughout the retention period
- Digital storage is allowed, but **integrity and authenticity** must be guaranteed
- Records must be **accessible for audit** by the Belastingdienst at any time

### Key Principle

The Belastingdienst requires you to store invoices **in the format you received them**. If a vendor sends a PDF, storing the PDF is legally compliant. There is no obligation to convert PDFs to XML.

## E-Invoicing Standards in the Netherlands

### Standards Stack

| Standard           | Scope    | Description                                                                     |
| ------------------ | -------- | ------------------------------------------------------------------------------- |
| **EN 16931**       | European | EU semantic data model for electronic invoices                                  |
| **NLCIUS**         | Dutch    | Netherlands Core Invoice Usage Specification — Dutch implementation of EN 16931 |
| **Peppol BIS 3.0** | Network  | Delivery specification for sending invoices via the Peppol network              |
| **UBL 2.1**        | Format   | The XML syntax used by NLCIUS                                                   |

### NLCIUS CustomizationID

```
urn:cen.eu:en16931:2017#compliant#urn:fdc:nen.nl:nlcius:v1.0
```

### Current Mandate Status (April 2026)

| Transaction Type                 | E-Invoicing Status                                                  |
| -------------------------------- | ------------------------------------------------------------------- |
| **B2G** (Business-to-Government) | **Mandatory** since 2017/2019 — must be UBL via Peppol or Digipoort |
| **B2B** (Business-to-Business)   | **Voluntary** — PDF, paper, and XML all accepted                    |
| **B2C** (Business-to-Consumer)   | **Not required**                                                    |

### Future Direction

The EU's **VAT in the Digital Age (ViDA)** directive is expected to make B2B e-invoicing mandatory across the EU in the coming years. The Netherlands is likely to follow.

## PDF vs XML/UBL — Value Analysis for myAdmin

### Current Invoice Pipeline (PDF)

```
PDF arrives → AI extraction (OpenRouter) → manual review → database
```

### Potential UBL Pipeline

```
XML arrives → parse structured fields → auto-import → database
```

### Comparison

| Aspect                | PDF                             | XML/UBL                  |
| --------------------- | ------------------------------- | ------------------------ |
| Machine-readable      | No — requires OCR/AI            | Yes — structured data    |
| Extraction accuracy   | ~85-95%                         | 100%                     |
| Processing cost       | OpenRouter API call per invoice | Zero — XML parsing only  |
| Vendor onboarding     | AI handles any vendor           | One universal UBL parser |
| Legal compliance (NL) | Accepted for B2B today          | Required for B2G         |
| Storage size          | ~100KB-2MB per invoice          | ~2-10KB per invoice      |

### Key Insight

The value is **not** in converting existing PDFs to XML. It's in having a second, more reliable intake channel that bypasses the AI extraction pipeline when structured data is already available.

## Decision: What to Build

### Do Build

1. **UBL invoice import** — Accept and parse UBL/XML invoices when vendors send them, skipping AI extraction entirely
2. **Keep PDF pipeline** — Most vendors still send PDFs; the current OpenRouter + vendor parser flow remains the primary channel
3. **XAF export** (future) — Export financial data as Auditfile Financieel (XAF 4.0) from the database when the Belastingdienst requests it
4. **UBL generation** (future, if needed) — Only if myAdmin needs to send invoices to Dutch government bodies

### Do NOT Build

- **PDF-to-XML conversion** — Redundant (data already extracted to database), expensive (still needs AI first), and no legal benefit

## Sample Files

- `mediamarkt.xml` — NLCIUS-compliant UBL 2.1 sample invoice (MediaMarkt Hoofddorp → Goodwin Solutions)

## Sources

- [Klippa — E-Invoicing & NLCIUS in the Netherlands](https://www.klippa.com/en/blog/information/e-invoicing-nlcius/)
- [DDD Invoices — Fiscalization in the Netherlands](https://dddinvoices.com/learn/fiscalization-and-real-time-reporting-in-the-netherlands)
- [Ecosio — E-invoicing in The Netherlands](https://ecosio.com/en/blog/e-invoicing-in-the-netherlands-an-overview/)
- [Sovos — Netherlands E-Invoicing](https://sovos.com/vat/tax-rules/netherlands-e-invoicing/)
- [Avalara — Netherlands E-Invoicing](https://www.avalara.com/us/en/vatlive/country-guides/europe/netherlands/netherlands-e-invoicing.html)

_Content was rephrased for compliance with licensing restrictions._
