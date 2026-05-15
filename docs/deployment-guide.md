# Deployment Guide

Deployment is not active in Milestone 1.1.

Required before staging:
- Configure Supabase project and apply `supabase/schema.sql`.
- Configure secret storage and Supabase Vault for raw email body encryption.
- Configure GitHub branch protection on `main`.
- Require CI checks: lint, format, typecheck, tests, and secret scan.
- Configure OAuth apps with least-privilege scopes.
