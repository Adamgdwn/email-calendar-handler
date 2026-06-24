# Deployment Guide

Deployment is not active in Milestone 1.1.

Required before staging:
- Configure Supabase project and apply `supabase/schema.sql`.
- Configure secret storage and Supabase Vault for raw email body encryption.
- Configure GitHub branch protection on `main`.
- Require CI checks: lint, format, typecheck, tests, and secret scan.
- Configure Microsoft Entra app registration with least-privilege Graph mail
  scopes before the first Outlook test account is connected.
- Add Gmail OAuth configuration only after Outlook ingestion passes Milestone 1.2.
