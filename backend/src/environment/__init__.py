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

from .app_env import AppEnv, parse_app_env, EnvironmentConfigError
from .environment_definition import (
    CognitoDef,
    MysqlDef,
    SamDef,
    PlaneDef,
    EnvironmentDefinition,
    ENVIRONMENT_DEFINITION,
)
from .resolver import (
    ResolvedCognito,
    ResolvedDbTarget,
    ResolvedSam,
    ResolvedConfig,
    resolve,
)
from .consistency_guard import (
    PlaneCheck,
    ConsistencyReport,
    build_consistency_report,
    run_consistency_guard,
    consistency_guard_startup_hook,
)
from .bootstrap import (
    bootstrap_environment,
    RESOLVED_ENV_CONFIG_KEY,
    APP_ENV_CONFIG_KEY,
)
from .health_report import build_environment_report

__all__ = [
    "AppEnv",
    "parse_app_env",
    "EnvironmentConfigError",
    "CognitoDef",
    "MysqlDef",
    "SamDef",
    "PlaneDef",
    "EnvironmentDefinition",
    "ENVIRONMENT_DEFINITION",
    "PlaneCheck",
    "ConsistencyReport",
    "build_consistency_report",
    "run_consistency_guard",
    "consistency_guard_startup_hook",
    "ResolvedCognito",
    "ResolvedDbTarget",
    "ResolvedSam",
    "ResolvedConfig",
    "resolve",
    "bootstrap_environment",
    "RESOLVED_ENV_CONFIG_KEY",
    "APP_ENV_CONFIG_KEY",
    "build_environment_report",
]