#!/usr/bin/env bash
# pre-commit hook: STEP parse gate on staged .stp/.step/.p21 files.
#
# .pre-commit-config.yaml (in the MODELS repo):
#
#   repos:
#     - repo: local
#       hooks:
#         - id: step-check
#           name: stepper check (parse gate)
#           entry: step-check.sh          # copy or link this script
#           language: system
#           files: '\.(stp|step|p21)$'
#
# Parse failures block the commit. Schema/semantic findings print as
# warnings (flip to strict by setting STEPPER_SEMANTIC=strict).
set -uo pipefail

sem="${STEPPER_SEMANTIC:-advisory}"
rc=0
for f in "$@"; do
  stepper check "$f" --semantic "$sem" || rc=1
done
exit $rc