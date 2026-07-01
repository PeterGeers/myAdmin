"""
Template PDF Renderer

Handles sample data fetching and preparation for template rendering,
including data that feeds into PDF generation pipelines.

Extracted from template_preview_service.py for maintainability.
"""

import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TemplatePdfRenderer:
    """
    Provides sample data fetching and field mapping generation for template rendering.

    Handles:
    - Fetching real sample data from database for different template types
    - Providing placeholder data when no real data is available
    - Auto-generating field mappings from template content
    """

    def __init__(self, db_manager, administration: str):
        """
        Initialize the template PDF renderer.

        Args:
            db_manager: DatabaseManager instance for database operations
            administration: The tenant/administration identifier
        """
        self.db = db_manager
        self.administration = administration

    def fetch_str_invoice_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent STR booking for invoice preview.

        Queries the vw_bnb_total view for the most recent booking (including future)
        for the current administration. Falls back to placeholder data if
        no bookings are found.

        Returns:
            Dictionary with 'data' and 'metadata' keys, or None if no data found
        """
        try:
            query = """
                SELECT 
                    reservationCode,
                    guestName,
                    channel,
                    listing,
                    checkinDate,
                    checkoutDate,
                    nights,
                    guests,
                    amountGross,
                    amountNett,
                    amountChannelFee,
                    amountTouristTax,
                    amountVat,
                    status
                FROM vw_bnb_total
                WHERE administration = %s
                ORDER BY checkinDate DESC
                LIMIT 1
            """

            results = self.db.execute_query(query, (self.administration,))

            if not results or len(results) == 0:
                logger.warning(
                    f"No STR bookings found for administration '{self.administration}'"
                )
                return self.get_placeholder_str_data()

            booking = results[0]

            # Prepare invoice data using the generator
            from report_generators.str_invoice_generator import prepare_invoice_data

            invoice_data = prepare_invoice_data(booking)

            # Generate invoice number (simplified - should use proper invoice numbering)
            invoice_data["invoice_number"] = (
                f"INV-{booking.get('reservationCode', 'UNKNOWN')}"
            )

            # Add status to metadata for transparency
            booking_status = booking.get("status", "unknown")

            return {
                "data": invoice_data,
                "metadata": {
                    "source": "database",
                    "record_date": str(booking.get("checkinDate", "")),
                    "record_id": booking.get("reservationCode", ""),
                    "booking_status": booking_status,
                    "message": f"Using most recent booking (status: {booking_status})",
                },
            }

        except Exception as e:
            logger.error(f"Failed to fetch STR invoice sample: {e}")
            return self.get_placeholder_str_data()

    def fetch_btw_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent BTW (VAT) data for preview.

        Retrieves balance and quarter data for the most recent quarter
        with available data. Uses the BTW aangifte generator to prepare
        the data in the correct format.

        Returns:
            Dictionary with 'data' and 'metadata' keys, or None if no data found
        """
        try:
            # Get most recent year and quarter with data
            current_year = datetime.now().year
            current_quarter = (datetime.now().month - 1) // 3 + 1

            # Try to generate report using the actual generator
            try:
                from report_generators.btw_aangifte_generator import (
                    generate_btw_report,
                    prepare_template_data,
                )
                from cache.mutaties_cache import MutatiesCache

                # Initialize cache
                cache = MutatiesCache()

                # Generate report
                report_data = generate_btw_report(
                    cache=cache,
                    db=self.db,
                    administration=self.administration,
                    year=current_year,
                    quarter=current_quarter,
                )

                if report_data.get("success"):
                    # Prepare template data
                    template_data = prepare_template_data(report_data)

                    return {
                        "data": template_data,
                        "metadata": {
                            "source": "database",
                            "record_date": f"{current_year}-Q{current_quarter}",
                            "record_id": f"BTW-{current_year}-Q{current_quarter}",
                            "message": "Using most recent quarter data",
                        },
                    }
                else:
                    logger.warning(
                        f"BTW report generation failed: {report_data.get('error')}"
                    )

            except ImportError as ie:
                logger.warning(f"Could not import BTW generator: {ie}")
            except Exception as ge:
                logger.warning(f"BTW report generation error: {ge}")

            # Fallback to placeholder data
            sample_data = {
                "year": str(current_year),
                "quarter": str(current_quarter),
                "administration": self.administration,
                "balance_rows": '<tr><td>2010</td><td>BTW te betalen</td><td class="amount">€1,000.00</td></tr>',
                "quarter_rows": '<tr><td>2020</td><td>BTW ontvangen</td><td class="amount">€500.00</td></tr>',
                "payment_instruction": "€500 te betalen",
                "generated_date": datetime.now().strftime("%d-%m-%Y"),
            }

            return {
                "data": sample_data,
                "metadata": {
                    "source": "placeholder",
                    "record_date": f"{current_year}-Q{current_quarter}",
                    "record_id": f"BTW-{current_year}-Q{current_quarter}",
                    "message": "Using placeholder data - no real data available",
                },
            }

        except Exception as e:
            logger.error(f"Failed to fetch BTW sample: {e}")
            return None

    def fetch_aangifte_ib_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent Aangifte IB (income tax) data for preview.

        Retrieves income tax data for the most recent year with available data.
        Uses the Aangifte IB generator to prepare the data in the correct format.

        Returns:
            Dictionary with 'data' and 'metadata' keys, or None if no data found
        """
        try:
            # Use previous year as current year data may not be complete
            current_year = datetime.now().year - 1

            # Try to generate report using the actual generator
            try:
                from report_generators.aangifte_ib_generator import generate_table_rows
                from cache.mutaties_cache import MutatiesCache

                # Initialize cache
                cache = MutatiesCache()

                # Get report data from cache
                df = cache.get_data(self.db)

                # Filter by year and administration
                df_filtered = df[
                    (df["jaar"] == current_year)
                    & (df["administration"].str.startswith(self.administration))
                ].copy()

                if len(df_filtered) > 0:
                    # Generate table rows
                    table_rows = generate_table_rows(
                        report_data=df_filtered.to_dict("records"),
                        cache=cache,
                        year=current_year,
                        administration=self.administration,
                        user_tenants=[self.administration],
                    )

                    sample_data = {
                        "year": str(current_year),
                        "administration": self.administration,
                        "table_rows": table_rows,
                        "generated_date": datetime.now().strftime("%d-%m-%Y"),
                    }

                    return {
                        "data": sample_data,
                        "metadata": {
                            "source": "database",
                            "record_date": str(current_year),
                            "record_id": f"IB-{current_year}",
                            "message": f"Using data from year {current_year}",
                        },
                    }
                else:
                    logger.warning(
                        f"No Aangifte IB data found for {self.administration} in {current_year}"
                    )

            except ImportError as ie:
                logger.warning(f"Could not import Aangifte IB generator: {ie}")
            except Exception as ge:
                logger.warning(f"Aangifte IB report generation error: {ge}")

            # Fallback to placeholder data
            sample_data = {
                "year": str(current_year),
                "administration": self.administration,
                "table_rows": '<tr><td>8001</td><td>Omzet</td><td class="amount">€50,000.00</td></tr>',
                "generated_date": datetime.now().strftime("%d-%m-%Y"),
            }

            return {
                "data": sample_data,
                "metadata": {
                    "source": "placeholder",
                    "record_date": str(current_year),
                    "record_id": f"IB-{current_year}",
                    "message": "Using placeholder data - no real data available",
                },
            }

        except Exception as e:
            logger.error(f"Failed to fetch Aangifte IB sample: {e}")
            return None

    def fetch_toeristenbelasting_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent tourist tax data for preview.

        Retrieves tourist tax declaration data for the most recent year
        with available data. Uses the Toeristenbelasting generator to
        prepare the data in the correct format.

        Returns:
            Dictionary with 'data' and 'metadata' keys, or None if no data found
        """
        try:
            current_year = datetime.now().year

            # Try to generate report using the actual generator
            try:
                from report_generators.toeristenbelasting_generator import (
                    generate_toeristenbelasting_report,
                )
                from cache.mutaties_cache import MutatiesCache
                from cache.bnb_cache import BNBCache

                # Initialize caches
                cache = MutatiesCache()
                bnb_cache = BNBCache()

                # Generate report
                report_data = generate_toeristenbelasting_report(
                    cache=cache, bnb_cache=bnb_cache, db=self.db, year=current_year
                )

                if report_data.get("success"):
                    # Use template_data from the report
                    template_data = report_data.get("template_data", {})

                    return {
                        "data": template_data,
                        "metadata": {
                            "source": "database",
                            "record_date": str(current_year),
                            "record_id": f"TT-{current_year}",
                            "message": f"Using data from year {current_year}",
                        },
                    }
                else:
                    logger.warning(
                        f"Toeristenbelasting report generation failed: {report_data.get('error')}"
                    )

            except ImportError as ie:
                logger.warning(f"Could not import Toeristenbelasting generator: {ie}")
            except Exception as ge:
                logger.warning(f"Toeristenbelasting report generation error: {ge}")

            # Fallback to placeholder data
            sample_data = {
                "year": str(current_year),
                "contact_name": "Sample Contact",
                "contact_email": "contact@example.com",
                "nights_total": "100",
                "revenue_total": "€10,000.00",
                "tourist_tax_total": "€300.00",
                "generated_date": datetime.now().strftime("%d-%m-%Y"),
            }

            return {
                "data": sample_data,
                "metadata": {
                    "source": "placeholder",
                    "record_date": str(current_year),
                    "record_id": f"TT-{current_year}",
                    "message": "Using placeholder data - no real data available",
                },
            }

        except Exception as e:
            logger.error(f"Failed to fetch tourist tax sample: {e}")
            return None

    def fetch_generic_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch generic placeholder data for unknown template types.

        This method provides fallback data when the template type is not
        recognized or when specific sample data fetching fails. It ensures
        that preview generation can always proceed with some data.

        Returns:
            Dictionary with 'data' and 'metadata' keys
        """
        logger.info(
            f"Using generic placeholder data for administration '{self.administration}'"
        )

        sample_data = {
            "administration": self.administration,
            "generated_date": datetime.now().strftime("%d-%m-%Y"),
            "year": str(datetime.now().year),
            "sample_text": "Sample Data",
            "sample_number": "1,234.56",
            "sample_currency": "€1,234.56",
            "company_name": "Sample Company",
            "contact_email": "contact@example.com",
        }

        return {
            "data": sample_data,
            "metadata": {
                "source": "placeholder",
                "record_date": datetime.now().strftime("%Y-%m-%d"),
                "record_id": "GENERIC-SAMPLE",
                "message": "Using generic placeholder data - template type not recognized",
            },
        }

    def get_placeholder_str_data(self) -> Dict[str, Any]:
        """
        Get placeholder STR invoice data when no real data is available.

        This method provides fallback invoice data with realistic sample values
        to ensure preview generation can proceed even when no bookings exist
        in the database.

        Returns:
            Dictionary with 'data' and 'metadata' keys
        """
        logger.info(
            f"Using placeholder STR invoice data for administration '{self.administration}'"
        )

        placeholder_data = {
            "invoice_number": "INV-2026-001",
            "reservationCode": "RES-SAMPLE-001",
            "guestName": "Sample Guest",
            "channel": "Booking.com",
            "listing": "Sample Property",
            "checkinDate": "01-01-2026",
            "checkoutDate": "05-01-2026",
            "nights": 4,
            "guests": 2,
            "amountGross": 500.00,
            "amountTouristTax": 15.00,
            "amountChannelFee": 50.00,
            "amountNett": 435.00,
            "amountVat": 0.00,
            "net_amount": 485.00,
            "tourist_tax": 15.00,
            "vat_amount": 0.00,
            "billing_name": "Sample Guest",
            "billing_address": "Via Booking.com",
            "billing_city": "Reservering: RES-SAMPLE-001",
            "invoice_date": datetime.now().strftime("%d-%m-%Y"),
            "due_date": datetime.now().strftime("%d-%m-%Y"),
            "company_name": "Jabaki a Goodwin Solutions Company",
            "company_address": "Beemsterstraat 3",
            "company_postal_city": "2131 ZA Hoofddorp",
            "company_country": "Nederland",
            "company_vat": "NL812613764B02",
            "company_coc": "24352408",
            "contact_email": "peter@jabaki.nl",
        }

        return {
            "data": placeholder_data,
            "metadata": {
                "source": "placeholder",
                "message": "No bookings found, using placeholder data",
                "record_date": datetime.now().strftime("%Y-%m-%d"),
                "record_id": "PLACEHOLDER",
            },
        }

    def generate_default_field_mappings(
        self, template_type: str, template_content: str
    ) -> Dict[str, Any]:
        """
        Auto-generate default field_mappings by extracting placeholders from template.

        Args:
            template_type: Type of template
            template_content: Template HTML content

        Returns:
            Dictionary with default field_mappings structure
        """
        try:
            logger.info(
                f"Generating default field_mappings for template type '{template_type}'"
            )

            # Extract all placeholders from template
            placeholders = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", template_content))

            # Define static company fields
            static_fields = {
                "company_name": "Jabaki a Goodwin Solutions Company",
                "company_address": "Beemsterstraat 3",
                "company_postal_city": "2131 ZA Hoofddorp",
                "company_country": "Netherlands"
                if "en" in template_type
                else "Nederland",
                "company_vat": "NL812613764B02",
                "company_coc": "24352408",
                "contact_email": "peter@jabaki.nl",
            }

            # Define field formats based on common naming patterns
            def get_field_format(field_name: str) -> str:
                if (
                    "amount" in field_name.lower()
                    or "tax" in field_name.lower()
                    or "vat" in field_name.lower()
                ):
                    return "currency"
                elif "date" in field_name.lower():
                    return "date"
                elif field_name in ["nights", "guests"]:
                    return "number"
                else:
                    return "text"

            # Build fields configuration
            fields = {}
            for placeholder in placeholders:
                if placeholder in static_fields:
                    # Static company field
                    fields[placeholder] = {
                        "path": placeholder,
                        "format": "text",
                        "source": "static",
                        "default": static_fields[placeholder],
                    }
                elif placeholder == "table_rows":
                    # Special calculated field
                    fields[placeholder] = {
                        "path": placeholder,
                        "format": "text",
                        "source": "calculation",
                        "default": "",
                    }
                else:
                    # Database field
                    field_format = get_field_format(placeholder)
                    fields[placeholder] = {
                        "path": placeholder,
                        "format": field_format,
                        "source": "database",
                        "default": 0 if field_format in ["currency", "number"] else "",
                    }

                    # Add transform for currency fields
                    if field_format == "currency":
                        fields[placeholder]["transform"] = "round"

            # Build complete field_mappings structure
            field_mappings = {
                "fields": fields,
                "formatting": {
                    "locale": "en_US" if "en" in template_type else "nl_NL",
                    "currency": "EUR",
                    "date_format": "DD-MM-YYYY",
                    "number_decimals": 2,
                },
                "conditionals": [],
            }

            # Add conditionals for STR invoices
            if "str_invoice" in template_type:
                field_mappings["conditionals"] = [
                    {
                        "field": "vat_amount",
                        "operator": "gt",
                        "value": 0,
                        "action": "show",
                    },
                    {
                        "field": "tourist_tax",
                        "operator": "gt",
                        "value": 0,
                        "action": "show",
                    },
                ]

            logger.info(f"Generated field_mappings with {len(fields)} fields")

            return field_mappings

        except Exception as e:
            logger.error(f"Failed to generate default field_mappings: {e}")
            # Return minimal fallback
            return {
                "fields": {},
                "formatting": {
                    "locale": "nl_NL",
                    "currency": "EUR",
                    "date_format": "DD-MM-YYYY",
                    "number_decimals": 2,
                },
                "conditionals": [],
            }
