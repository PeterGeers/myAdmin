"""
PivotModelStore — CRUD persistence layer for saved pivot model definitions.

Stores pivot configurations as JSON documents in the ``pivot_models`` table.
All operations enforce tenant isolation via the ``administration`` column.

Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 5.1–5.6, 10.1–10.4
Reference: .kiro/specs/dynamic-pivot-views/design.md §2 PivotModelStore
"""

import json
import logging
from typing import List

logger = logging.getLogger(__name__)

# Required top-level fields in a pivot model definition.
REQUIRED_DEFINITION_FIELDS = ("data_source", "group_columns", "aggregate_measures")


class PivotModelStore:
    """Persistence layer for pivot model definitions."""

    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance.
        """
        self.db = db

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def save_model(
        self, tenant: str, user_email: str, name: str, definition: dict
    ) -> dict:
        """
        Save a new pivot model.

        Args:
            tenant: administration identifier (tenant isolation).
            user_email: email of the creating user.
            name: human-readable model name.
            definition: pivot configuration dict.

        Returns:
            ``{success: True, id: <int>}``

        Raises:
            ValueError: if *name* already exists for this user+tenant, or
                if *definition* fails validation.
        """
        self.validate_definition(definition)

        # Check for duplicate name (same tenant + user + name)
        existing = self.db.execute_query(
            "SELECT id FROM pivot_models "
            "WHERE administration = %s AND created_by = %s AND name = %s",
            (tenant, user_email, name),
            fetch=True,
        )
        if existing:
            raise ValueError(f"A model with name '{name}' already exists")

        json_def = self.serialize(definition)
        data_source = definition.get("data_source", "")

        new_id = self.db.execute_query(
            "INSERT INTO pivot_models (administration, name, data_source, definition, created_by) "
            "VALUES (%s, %s, %s, %s, %s)",
            (tenant, name, data_source, json_def, user_email),
            fetch=False,
            commit=True,
        )

        return {"success": True, "id": new_id}

    def update_model(
        self, tenant: str, user_email: str, model_id: int, definition: dict
    ) -> dict:
        """
        Update an existing model's definition.

        Args:
            tenant: administration identifier.
            user_email: email of the requesting user.
            model_id: primary key of the model to update.
            definition: new pivot configuration dict.

        Returns:
            ``{success: True}``

        Raises:
            ValueError: if model not found or definition invalid.
        """
        self.validate_definition(definition)

        # Verify model exists and belongs to this tenant
        existing = self.db.execute_query(
            "SELECT id FROM pivot_models WHERE id = %s AND administration = %s",
            (model_id, tenant),
            fetch=True,
        )
        if not existing:
            raise ValueError("Pivot model not found")

        json_def = self.serialize(definition)
        data_source = definition.get("data_source", "")

        self.db.execute_query(
            "UPDATE pivot_models SET definition = %s, data_source = %s, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = %s AND administration = %s",
            (json_def, data_source, model_id, tenant),
            fetch=False,
            commit=True,
        )

        return {"success": True}

    def load_model(self, tenant: str, model_id: int) -> dict:
        """
        Load a single model by ID.

        Args:
            tenant: administration identifier.
            model_id: primary key.

        Returns:
            Dict with model metadata and deserialized definition.

        Raises:
            ValueError: if model not found or definition is malformed.
        """
        rows = self.db.execute_query(
            "SELECT id, administration, name, data_source, definition, "
            "created_by, created_at, updated_at "
            "FROM pivot_models WHERE id = %s AND administration = %s",
            (model_id, tenant),
            fetch=True,
        )
        if not rows:
            raise ValueError("Pivot model not found")

        row = rows[0]
        definition = self.deserialize(row["definition"])

        return {
            "id": row["id"],
            "name": row["name"],
            "data_source": row["data_source"],
            "definition": definition,
            "created_by": row["created_by"],
            "created_at": str(row["created_at"]) if row["created_at"] else None,
            "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
        }

    def list_models(self, tenant: str) -> List[dict]:
        """
        List all models for a tenant (summary view).

        Args:
            tenant: administration identifier.

        Returns:
            List of dicts with ``id``, ``name``, ``data_source``,
            ``created_by``, ``created_at``.
        """
        rows = self.db.execute_query(
            "SELECT id, name, data_source, created_by, created_at "
            "FROM pivot_models WHERE administration = %s "
            "ORDER BY name",
            (tenant,),
            fetch=True,
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "data_source": r["data_source"],
                "created_by": r["created_by"],
                "created_at": str(r["created_at"]) if r["created_at"] else None,
            }
            for r in rows
        ]

    def delete_model(self, tenant: str, model_id: int) -> bool:
        """
        Delete a model.

        Args:
            tenant: administration identifier.
            model_id: primary key.

        Returns:
            ``True`` if a row was deleted, ``False`` otherwise.
        """
        result = self.db.execute_query(
            "DELETE FROM pivot_models WHERE id = %s AND administration = %s",
            (model_id, tenant),
            fetch=False,
            commit=True,
        )
        return result is not None and result > 0

    # ------------------------------------------------------------------
    # Serialization helpers (static)
    # ------------------------------------------------------------------

    @staticmethod
    def serialize(definition: dict) -> str:
        """
        Serialize a pivot model definition to a JSON string.

        Args:
            definition: pivot configuration dict.

        Returns:
            JSON string.
        """
        return json.dumps(definition, ensure_ascii=False)

    @staticmethod
    def deserialize(json_str) -> dict:
        """
        Deserialize a JSON string (or dict) to a pivot model definition.

        Validates that all required fields are present.

        Args:
            json_str: JSON string or already-parsed dict.

        Returns:
            Validated definition dict.

        Raises:
            ValueError: if the input is malformed or missing required fields.
        """
        if isinstance(json_str, dict):
            definition = json_str
        elif isinstance(json_str, str):
            try:
                definition = json.loads(json_str)
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"Invalid JSON in model definition: {e}") from e
        else:
            raise ValueError(
                f"Expected JSON string or dict, got {type(json_str).__name__}"
            )

        if not isinstance(definition, dict):
            raise ValueError("Model definition must be a JSON object")

        # Validate required fields
        PivotModelStore.validate_definition(definition)

        return definition

    @staticmethod
    def validate_definition(definition: dict) -> None:
        """
        Validate that a pivot model definition has all required fields.

        Required:
        - ``data_source``: non-empty string
        - ``group_columns``: non-empty list
        - ``aggregate_measures``: non-empty list

        Raises:
            ValueError: with a descriptive message if validation fails.
        """
        if not isinstance(definition, dict):
            raise ValueError("Model definition must be a dict")

        # data_source
        ds = definition.get("data_source")
        if not ds or not isinstance(ds, str):
            raise ValueError(
                "Invalid model definition: missing required field 'data_source'"
            )

        # group_columns
        gc = definition.get("group_columns")
        if not gc or not isinstance(gc, list) or len(gc) == 0:
            raise ValueError(
                "Invalid model definition: 'group_columns' must be a non-empty list"
            )

        # aggregate_measures
        am = definition.get("aggregate_measures")
        if not am or not isinstance(am, list) or len(am) == 0:
            raise ValueError(
                "Invalid model definition: 'aggregate_measures' must be a non-empty list"
            )
