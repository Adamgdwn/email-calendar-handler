#!/usr/bin/env bash

set -euo pipefail

repo_root="${1:-$(pwd)}"
control_file="${repo_root}/project-control.yaml"

required_files=(
  "README.md"
  "docs/architecture.md"
  "docs/manual.md"
  "docs/roadmap.md"
  "docs/deployment-guide.md"
  "docs/runbook.md"
  "docs/CHANGELOG.md"
  "docs/risks/risk-register.md"
  "pyproject.toml"
  ".pre-commit-config.yaml"
  "supabase/schema.sql"
)

if [[ ! -f "${control_file}" ]]; then
  echo "Missing project-control.yaml"
  exit 1
fi

for file in "${required_files[@]}"; do
  if [[ ! -f "${repo_root}/${file}" ]]; then
    echo "Missing required file: ${file}"
    exit 1
  fi
done

if ! grep -Eq "handles_sensitive_data:[[:space:]]*true" "${control_file}"; then
  echo "project-control.yaml must mark handles_sensitive_data: true"
  exit 1
fi

if ! grep -Eq "agent_controls:" "${control_file}" ||
  ! grep -Eq "applicable:[[:space:]]*true" "${control_file}"; then
  echo "project-control.yaml must enable applicable agent_controls"
  exit 1
fi

for control in required-file-check lint tests typecheck secret-scan; do
  if ! grep -Eq "[[:space:]]+- ${control}$" "${control_file}"; then
    echo "project-control.yaml missing machine enforcement: ${control}"
    exit 1
  fi
done

echo "Governance preflight passed."
