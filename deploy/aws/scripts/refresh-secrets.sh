#!/usr/bin/env bash
# ==============================================================================
# CRYPTIQ — SAFE SECRETS REFRESH SCRIPT
#
# Refreshes the GEMINI_API_KEY runtime configuration from AWS SSM Parameter Store
# into /opt/cryptiq/.env and restarts the backend container.
#
# ZERO-SECRETS GUARANTEE:
#   * Never prints, echoes, or logs the secret value.
#   * File is created with umask 077 and chmod 600.
#   * Backend container is restarted in-place — NO Docker image rebuild.
#   * SQLite database on /data is preserved across restarts.
#
# Usage:
#   1. Directly on the EC2 host (via SSM Session Manager):
#      bash /opt/cryptiq/app/deploy/aws/scripts/refresh-secrets.sh
#
#   2. Remotely from operator machine via AWS Systems Manager Run Command:
#      INSTANCE_ID=<id> AWS_REGION=<region> deploy/aws/scripts/refresh-secrets.sh
# ==============================================================================
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
PARAM_NAME="/cryptiq/GEMINI_API_KEY"
ENV_FILE="/opt/cryptiq/.env"
APP_DIR="${APP_DIR:-/opt/cryptiq/app}"
COMPOSE_FILE="deploy/aws/compose/docker-compose.aws.yml"

# Check if running locally on operator machine or on EC2 instance
if [ ! -d "/opt/cryptiq" ] && [ -n "${INSTANCE_ID:-}" ]; then
  echo "refresh-secrets: running remotely via AWS SSM Run Command on instance ${INSTANCE_ID} (${REGION})..."
  command_id=$(aws ssm send-command \
    --region "${REGION}" \
    --instance-ids "${INSTANCE_ID}" \
    --document-name "AWS-RunShellScript" \
    --comment "Refresh CRYPTIQ Gemini API key from SSM and restart backend" \
    --parameters 'commands=["bash /opt/cryptiq/app/deploy/aws/scripts/refresh-secrets.sh"]' \
    --query "Command.CommandId" \
    --output text)
  echo "refresh-secrets: dispatched SSM command ${command_id}. Waiting for completion..."
  aws ssm wait command-executed \
    --region "${REGION}" \
    --command-id "${command_id}" \
    --instance-id "${INSTANCE_ID}"
  echo "refresh-secrets: remote execution completed successfully."
  exit 0
fi

echo "refresh-secrets: querying SSM Parameter Store for ${PARAM_NAME} in region ${REGION}..."

mkdir -p /opt/cryptiq
umask 077
: > "${ENV_FILE}"

gemini_key="$(aws ssm get-parameter \
  --region "${REGION}" \
  --name "${PARAM_NAME}" \
  --with-decryption \
  --query Parameter.Value \
  --output text 2>/dev/null || true)"

if [ -n "${gemini_key}" ] && [ "${gemini_key}" != "None" ]; then
  printf 'GEMINI_API_KEY=%s\n' "${gemini_key}" >> "${ENV_FILE}"
  echo "refresh-secrets: GEMINI_API_KEY loaded from SSM (value not logged)."
else
  echo "refresh-secrets: notice — ${PARAM_NAME} not present in SSM; AI explanation remains disabled."
fi
unset gemini_key

chmod 600 "${ENV_FILE}"
chown root:root "${ENV_FILE}" 2>/dev/null || true

if [ -d "${APP_DIR}" ]; then
  cd "${APP_DIR}"
  echo "refresh-secrets: restarting backend service..."
  docker compose -f "${COMPOSE_FILE}" restart backend

  echo "refresh-secrets: waiting for backend health & readiness..."
  ready=0
  for attempt in $(seq 1 30); do
    if curl -fsS -o /dev/null --max-time 5 "http://127.0.0.1:8000/health/ready" 2>/dev/null || \
       curl -fsS -o /dev/null --max-time 5 "http://127.0.0.1/api/v1/health/ready" 2>/dev/null; then
      ready=1
      echo "refresh-secrets: backend healthy and ready."
      break
    fi
    sleep 2
  done

  if [ "${ready}" -ne 1 ]; then
    echo "refresh-secrets: WARNING backend did not become ready within 60s"
    docker compose -f "${COMPOSE_FILE}" ps
    exit 1
  fi
  echo "refresh-secrets: SUCCESS — runtime environment refreshed, Gemini active."
else
  echo "refresh-secrets: directory ${APP_DIR} not found; skipped container restart."
fi
