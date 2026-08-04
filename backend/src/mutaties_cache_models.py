"""
MutatiesCache data models.

Shared dataclass definitions used across mutaties_cache sub-modules.
"""

import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from typing import Set


@dataclass
class TenantCacheEntry:
    """Cache entry holding one tenant's mutation data."""

    data: pd.DataFrame
    last_accessed: datetime
    last_loaded: datetime
    years_loaded: Set[int] = field(default_factory=set)
