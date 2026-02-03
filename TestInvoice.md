{
  "conditionals": [
    {
      "action": "show",
      "field": "vat_amount",
      "operator": "gt",
      "value": 0
    },
    {
      "action": "show",
      "field": "tourist_tax",
      "operator": "gt",
      "value": 0
    }
  ],
  "fields": {
    "amountGross": {
      "default": 0,
      "format": "currency",
      "path": "amountGross",
      "source": "database",
      "transform": "round"
    },
    "billing_address": {
      "default": "",
      "format": "text",
      "path": "billing_address",
      "source": "database"
    },
    "billing_city": {
      "default": "",
      "format": "text",
      "path": "billing_city",
      "source": "database"
    },
    "billing_name": {
      "default": "",
      "format": "text",
      "path": "billing_name",
      "source": "database"
    },
    "channel": {
      "default": "",
      "format": "text",
      "path": "channel",
      "source": "database"
    },
    "checkinDate": {
      "default": "",
      "format": "date",
      "path": "checkinDate",
      "source": "database"
    },
    "checkoutDate": {
      "default": "",
      "format": "date",
      "path": "checkoutDate",
      "source": "database"
    },
    "company_address": {
      "default": "Beemsterstraat 3",
      "format": "text",
      "path": "company_address",
      "source": "static"
    },
    "company_coc": {
      "default": "24352408",
      "format": "text",
      "path": "company_coc",
      "source": "static"
    },
    "company_country": {
      "default": "Netherlands",
      "format": "text",
      "path": "company_country",
      "source": "static"
    },
    "company_name": {
      "default": "Jabaki a Goodwin Solutions Company",
      "format": "text",
      "path": "company_name",
      "source": "static"
    },
    "company_postal_city": {
      "default": "2131 ZA Hoofddorp",
      "format": "text",
      "path": "company_postal_city",
      "source": "static"
    },
    "company_vat": {
      "default": "NL812613764B02",
      "format": "text",
      "path": "company_vat",
      "source": "static"
    },
    "contact_email": {
      "default": "peter@jabaki.nl",
      "format": "text",
      "path": "contact_email",
      "source": "static"
    },
    "due_date": {
      "default": "",
      "format": "date",
      "path": "due_date",
      "source": "database"
    },
    "guestName": {
      "default": "",
      "format": "text",
      "path": "guestName",
      "source": "database"
    },
    "guests": {
      "default": 0,
      "format": "number",
      "path": "guests",
      "source": "database"
    },
    "invoice_date": {
      "default": "",
      "format": "date",
      "path": "invoice_date",
      "source": "database"
    },
    "listing": {
      "default": "",
      "format": "text",
      "path": "listing",
      "source": "database"
    },
    "net_amount": {
      "default": 0,
      "format": "currency",
      "path": "net_amount",
      "source": "database",
      "transform": "round"
    },
    "nights": {
      "default": 0,
      "format": "number",
      "path": "nights",
      "source": "database"
    },
    "reservationCode": {
      "default": "",
      "format": "text",
      "path": "reservationCode",
      "source": "database"
    },
    "table_rows": {
      "default": "",
      "format": "text",
      "path": "table_rows",
      "source": "calculation"
    },
    "tourist_tax": {
      "default": 0,
      "format": "currency",
      "path": "tourist_tax",
      "source": "database",
      "transform": "round"
    },
    "vat_amount": {
      "default": 0,
      "format": "currency",
      "path": "vat_amount",
      "source": "database",
      "transform": "round"
    }
  },
  "formatting": {
    "currency": "EUR",
    "date_format": "DD-MM-YYYY",
    "locale": "en_US",
    "number_decimals": 2
  }
}