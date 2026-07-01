"""Cell styling and formatting utilities for XLSX export.

Provides reusable style definitions and cell formatting functions
used by the XLSX export processor.
"""

from openpyxl.styles import Font, Border, Side


# --- Style Definitions ---

HEADER_FONT = Font(bold=True)

THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

AMOUNT_NUMBER_FORMAT = "0.00"


# --- Formatting Functions ---


def apply_header_style(worksheet):
    """Apply bold font and thin border to the header row (row 1).

    Args:
        worksheet: openpyxl Worksheet object with data already written
    """
    for cell in worksheet[1]:
        cell.font = HEADER_FONT
        cell.border = THIN_BORDER


def format_amount_column(worksheet):
    """Find the 'Amount' column and apply number formatting to all data cells.

    Args:
        worksheet: openpyxl Worksheet object with header in row 1
    """
    amount_col = None
    for idx, cell in enumerate(worksheet[1], 1):
        if cell.value == "Amount":
            amount_col = idx
            break

    if amount_col:
        for row in range(2, worksheet.max_row + 1):
            cell = worksheet.cell(row=row, column=amount_col)
            if cell.value is not None:
                cell.number_format = AMOUNT_NUMBER_FORMAT


def apply_worksheet_formatting(worksheet):
    """Apply all standard formatting to a data worksheet.

    Applies header styling, amount column formatting, and autofilter.

    Args:
        worksheet: openpyxl Worksheet object with data already written
    """
    apply_header_style(worksheet)
    format_amount_column(worksheet)
    worksheet.auto_filter.ref = worksheet.dimensions
