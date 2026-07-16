-- Dev-only bootstrap of the least-privilege application role.
--
-- WHY THIS EXISTS: Postgres superusers (and BYPASSRLS roles) ignore Row-Level
-- Security *unconditionally* — ENABLE/FORCE ROW LEVEL SECURITY does not apply to
-- them. The docker image makes POSTGRES_USER a superuser, so if the app connected
-- as `keel`, tenant isolation would be silently disabled while every policy still
-- looked correct in pg_policies. The app therefore connects as `keel_app`:
-- non-superuser, no BYPASSRLS, not the table owner -> RLS always applies.
--
-- Roles are infrastructure, not schema: in production Terraform creates this role
-- with a secrets-manager password (PLAT-04). This file is local dev only; the
-- credential below is intentionally throwaway and never used outside compose.

CREATE ROLE keel_app LOGIN PASSWORD 'keel_app';
GRANT USAGE ON SCHEMA public TO keel_app;
