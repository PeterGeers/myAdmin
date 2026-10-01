"""
Tenant Language Service

This service manages tenant default language preferences stored in the database.
The default_language column was added to the tenants table in Phase 2.2 of i18n implementation.
"""

from database import DatabaseManager


def get_tenant_language(administration: str) -> str:
    """
    Get tenant's default language from database

    Args:
        administration: Tenant administration name

    Returns:
        str: Language code ('nl' or 'en'), defaults to 'nl' if not set
    """
    try:
        db_manager = DatabaseManager()
        # READ: plain (tuple-row) cursor — preserve index access via dictionary=False
        with db_manager.get_cursor(dictionary=False) as (cursor, conn):
            # Get tenant's default language
            cursor.execute(
                """
                SELECT default_language
                FROM tenants
                WHERE administration = %s
            """,
                (administration,),
            )

            result = cursor.fetchone()

        if result and result[0]:
            language = result[0]
            print(
                f"✅ Retrieved default language for tenant {administration}: {language}"
            )
            return language

        # Default to Dutch if not set
        print(
            f"ℹ️ No default language set for tenant {administration}, defaulting to 'nl'"
        )
        return "nl"

    except Exception as e:
        print(f"❌ Error getting tenant language: {e}")
        return "nl"


def update_tenant_language(administration: str, language: str) -> bool:
    """
    Update tenant's default language in database

    Args:
        administration: Tenant administration name
        language: Language code ('nl' or 'en')

    Returns:
        bool: True if successful, False otherwise
    """
    # Validate language code
    if language not in ["nl", "en"]:
        print(f"❌ Invalid language code: {language}. Must be 'nl' or 'en'")
        return False

    try:
        db_manager = DatabaseManager()
        # WRITE: transaction() auto-commits on success, rolls back on exception.
        # Only cursor.rowcount is consumed here (identical for tuple/dict cursors),
        # so the cursor flavor is irrelevant and the standard transaction() form applies.
        with db_manager.transaction() as (cursor, conn):
            # Update tenant's default language
            cursor.execute(
                """
                UPDATE tenants
                SET default_language = %s,
                    updated_at = NOW()
                WHERE administration = %s
            """,
                (language, administration),
            )

            rowcount = cursor.rowcount

        if rowcount > 0:
            print(
                f"✅ Updated default language for tenant {administration}: {language}"
            )
            return True
        else:
            print(f"❌ Tenant not found: {administration}")
            return False

    except Exception as e:
        print(f"❌ Error updating tenant language: {e}")
        return False


def validate_language_code(language: str) -> bool:
    """
    Validate language code

    Args:
        language: Language code to validate

    Returns:
        bool: True if valid, False otherwise
    """
    return language in ["nl", "en"]
