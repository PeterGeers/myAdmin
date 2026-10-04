"""
Environment module for myAdmin
Provides environment resolution, configuration, and consistency checking

Exports:
- AppEnv, parse_app_env, EnvironmentConfigError from app_env
- CognitoDef, MysqlDef, SamDef, PlaneDef, EnvironmentDefinition, ENVIRONMENT_DEFINITION from environment_definition
- PlaneCheck, ConsistencyReport, build_consistency_report, run_consistency_guard,
  consistency_guard_startup_hook from consistency_guard
- ResolvedCognito, ResolvedDbTarget, ResolvedSam, ResolvedConfig, resolve from resolver
- bootstrap_environment, RESOLVED_ENV_CONFIG_KEY, APP_ENV_CONFIG_KEY from bootstrap
- build_environment_report from health_report
"""

from .app_env import AppEnv, EnvironmentConfigError, parse_app_env
from .bootstrap import (
    APP_ENV_CONFIG_KEY,
    RESOLVED_ENV_CONFIG_KEY,
    bootstrap_environment,
)
from .consistency_guard import (
    ConsistencyReport,
    PlaneCheck,
    build_consistency_report,
    consistency_guard_startup_hook,
    run_consistency_guard,
)
from .environment_definition import (
    ENVIRONMENT_DEFINITION,
    CognitoDef,
    EnvironmentDefinition,
    MysqlDef,
    PlaneDef,
    SamDef,
)
from .health_report import build_environment_report
from .resolver import (
    ResolvedCognito,
    ResolvedConfig,
    ResolvedDbTarget,
    ResolvedSam,
    resolve,
)

__all__ = [
    "APP_ENV_CONFIG_KEY",
    "ENVIRONMENT_DEFINITION",
    "RESOLVED_ENV_CONFIG_KEY",
    "AppEnv",
    "CognitoDef",
    "ConsistencyReport",
    "EnvironmentConfigError",
    "EnvironmentDefinition",
    "MysqlDef",
    "PlaneCheck",
    "PlaneDef",
    "ResolvedCognito",
    "ResolvedConfig",
    "ResolvedDbTarget",
    "ResolvedSam",
    "SamDef",
    "bootstrap_environment",
    "build_consistency_report",
    "build_environment_report",
    "consistency_guard_startup_hook",
    "parse_app_env",
    "resolve",
    "run_consistency_guard",
]
