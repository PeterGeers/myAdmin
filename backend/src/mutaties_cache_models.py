"""
MutatiesCache data models.

Shared dataclass definitions used across mutaties_cache sub-modules.
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd


@dataclass
class TenantCacheEntry:
    """Cache entry holding one tenant's mutation data."""

    data: pd.DataFrame
    last_accessed: datetime
    last_loaded: datetime
    years_loaded: set[int] = field(default_factory=set)
