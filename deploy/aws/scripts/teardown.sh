#!/usr/bin/env bash
# ==============================================================================
# CRYPTIQ — TERRAFORM AWS TEARDOWN SCRIPT
# Destroys all billable AWS resources created by Terraform and cleans up
# any demo SSM parameters and log groups.
#
# Usage:
#   deploy/aws/scripts/teardown.sh
# ==============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${HERE}/../terraform"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

echo "teardown: starting CRYPTIQ teardown..."

if [ -d "${TF_DIR}" ]; then
  echo "teardown: running terraform destroy..."
  export TF_CLI_CONFIG_FILE="${TF_CLI_CONFIG_FILE:-/dev/null}"
  terraform -chdir="${TF_DIR}" destroy -auto-approve || true
fi

# Clean up optional SSM parameter if AWS CLI is installed
if command -v aws >/dev/null 2>&1; then
  echo "teardown: checking for optional SSM parameter..."
  aws ssm delete-parameter --region "${REGION}" --name /cryptiq/GEMINI_API_KEY >/dev/null 2>&1 \
    && echo "teardown: deleted /cryptiq/GEMINI_API_KEY" \
    || echo "teardown: /cryptiq/GEMINI_API_KEY not present or already deleted"

  echo "teardown: checking for leftover CloudWatch log groups..."
  for lg in /cryptiq/backend /cryptiq/frontend /cryptiq/nginx /cryptiq/bootstrap; do
    aws logs delete-log-group --region "${REGION}" --log-group-name "${lg}" >/dev/null 2>&1 \
      && echo "teardown: deleted ${lg}" || true
  done
fi

echo "teardown: COMPLETE — all demo infrastructure destroyed."
