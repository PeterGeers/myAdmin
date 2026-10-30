# load_dotenv() in database.py clobbers AWS_PROFILE → ops scripts silently hit the WRONG AWS account
> PROMOTED TO BUGFIX (2026-10-12) → `.kiro/specs/BUGS/20261012 load_dotenv clobbers AWS_PROFILE/analysis.md`.
> Decided fix: **(a) remove the import-time `load_dotenv` side-effect in `database.py` + (b) strip
> the static personal-account AWS keys from both `.env` and `backend/.env`** (option (c) ops-env
> helper rejected). Grounded re-check found the earlier `backend/.env` pin only MOVED the clobber
> (both files still export the static keys; `backend/.env` also exports the local DynamoDB
> endpoint), and that the local-DynamoDB path already defaults creds to `"local"` so (b)'s blast
> radius is small. This is the **prerequisite gate** before the Members `Parameter redesign` Phase 0
> (whose committed `project-config-to-prod.py` runner carries a `_restrip_aws_env()` workaround for
> THIS bug). Stays a standalone infra bugfix — NOT folded into the redesign.
