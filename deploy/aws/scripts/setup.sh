#!/usr/bin/env bash
# Put the OPTIONAL Gemini key into SSM Parameter Store as a SecureString.
#
#   GEMINI_API_KEY=... deploy/aws/scripts/setup.sh
#   # or run with no env var and paste when prompted (input is hidden)
#
# The demo works with no key at all — the AI explanation endpoint then returns
# a controlled 503 AI_EXPLANATION_UNAVAILABLE and every finding stays usable.
# GITHUB_TOKEN is deliberately NOT provisioned: the analyzer only reads public
# repositories for the demo.
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
PARAM_NAME="/cryptiq/GEMINI_API_KEY"

key="${GEMINI_API_KEY:-}"
if [ -z "${key}" ]; then
  read -rsp "Gemini API key (leave blank to skip): " key
  echo
fi

if [ -z "${key}" ]; then
  echo "setup: no key provided — skipping. The demo will run without AI explanations."
  exit 0
fi

aws ssm put-parameter \
  --region "${REGION}" \
  --name "${PARAM_NAME}" \
  --type SecureString \
  --value "${key}" \
  --overwrite >/dev/null

unset key
echo "setup: stored ${PARAM_NAME} (SecureString) in ${REGION}. Value not echoed."
echo "setup: the instance role grants ssm:GetParameter on /cryptiq/* + kms:Decrypt on alias/aws/ssm only."
