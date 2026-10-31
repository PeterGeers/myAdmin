# Common Overview

**Status**: Active
**Purpose**: Cross-cutting platform concerns shared across business modules — infrastructure,
identity, data/config, serverless, documentation, and shared UI/frameworks. Unlike the business
areas (FIN, STR, Members, …), `Common` is itself a grouping of sub-areas.

## Sub-areas

| Sub-area | Description | Link |
| --- | --- | --- |
| Security | Security specs, incident remediation, hardening. | [Security](Security) |
| Cognito | AWS Cognito identity, pools, groups, triggers. | [Cognito](Cognito) |
| AWS | General AWS account/service concerns. | [AWS](AWS) |
| CICD | CI/CD workflows and deploy pipelines. | [CICD](CICD) |
| terraform | Terraform IaC specs. | [terraform](terraform) |
| Database | Database schema, migrations, data access. | [Database](Database) |
| Caching | Caching layer. | [Caching](Caching) |
| concurrency-and-memory | Concurrency and memory behavior. | [concurrency-and-memory](concurrency-and-memory) |
| Docker local | Local Docker dev environment. | [Docker local](Docker%20local) |
| test-environment | Test environment / APP_ENV model. | [test-environment](test-environment) |
| Serverless-applications | SAM / serverless application specs. | [Serverless-applications](Serverless-applications) |
| MCP | Model Context Protocol server/config. | [MCP](MCP) |
| image-asset-management | Media asset lifecycle (S3 registry). Has `_archive/`. | [image-asset-management](image-asset-management) |
| Tenant | Tenant isolation and tenant-admin concerns. | [Tenant](Tenant) |
| Cognito/Tenant/invoice-lines-tenant-isolation | Tenant isolation for invoice lines. | [invoice-lines-tenant-isolation](invoice-lines-tenant-isolation) |
| parameter-driven-config | Parameter-driven configuration store. | [parameter-driven-config](parameter-driven-config) |
| ai-model-registry | AI model registry. | [ai-model-registry](ai-model-registry) |
| pivot-views-dynamic | Dynamic pivot views. | [pivot-views-dynamic](pivot-views-dynamic) |
| Reporting | Shared reporting concerns. | [Reporting](Reporting) |
| Chakra | Chakra UI usage/standards. | [Chakra](Chakra) |
| Frameworks | Framework-level standards. | [Frameworks](Frameworks) |
| navigation-restructure | Navigation restructure. | [navigation-restructure](navigation-restructure) |
| SysAdmin-Module | System-administration module. | [SysAdmin-Module](SysAdmin-Module) |
| Hooks | Agent/app hooks. | [Hooks](Hooks) |
| Internationalization | i18n / localization. | [Internationalization](Internationalization) |
| Graphics | Graphics assets/standards. | [Graphics](Graphics) |
| templates | Template system. | [templates](templates) |
| Google Drive | Google Drive integration. | [Google Drive](Google%20Drive) |
| Postman API testing | Postman API testing. | [Postman API testing](Postman%20API%20testing) |
| Project structure | Project structure conventions. | [Project structure](Project%20structure) |
| kiro-alignment | Kiro alignment / steering. | [kiro-alignment](kiro-alignment) |
| onboarding | Onboarding flows. | [onboarding](onboarding) |
| end-user-documentation | End-user documentation. | [end-user-documentation](end-user-documentation) |
| user-documentation-updates | User documentation updates. | [user-documentation-updates](user-documentation-updates) |
| LinuxMigration | Linux/WSL migration. | [LinuxMigration](LinuxMigration) |
| Railway migration | Railway migration. | [Railway migration](Railway%20migration) |

## Conventions

Completed specs for a sub-area move to that sub-area's `_archive/` and are marked
`"status": "done"` in their `.config.kiro` (see `image-asset-management/_archive/` for the worked
example). See the root [`.kiro/specs/README.md`](../README.md) for the overall model.
