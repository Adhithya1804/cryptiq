#!/usr/bin/env bash
# ==============================================================================
# CRYPTIQ — TERRAFORM AWS DEPLOYMENT SCRIPT
# Provisions the demo stack using Terraform and verifies external health.
#
# Usage:
#   deploy/aws/scripts/deploy.sh
#
# Optional environment variables:
#   AWS_REGION     (default us-east-1)
#   INSTANCE_TYPE  (default t3.medium)
#   ALLOWED_CIDR   (default 0.0.0.0/0)
#   REPO_URL       (default https://github.com/Adhithya1804/cryptiq.git)
#   REPO_REF       (default aws-demo-deploy-layer)
#   SKIP_HEALTH    (default 0 — set to 1 to skip external health checks)
# ==============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${HERE}/../terraform"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
ALLOWED_CIDR="${ALLOWED_CIDR:-0.0.0.0/0}"
REPO_URL="${REPO_URL:-https://github.com/Adhithya1804/cryptiq.git}"
REPO_REF="${REPO_REF:-aws-demo-deploy-layer}"

die() { echo "deploy: ERROR: $*" >&2; exit 1; }

# --- 1. Verify Prerequisites ------------------------------------------ #
for bin in terraform curl; do
  command -v "${bin}" >/dev/null 2>&1 || die "'${bin}' is required on PATH"
done

[ -d "${TF_DIR}" ] || die "Terraform directory not found at ${TF_DIR}"

echo "deploy: starting CRYPTIQ Terraform deployment..."
echo "deploy: region=${REGION} instance=${INSTANCE_TYPE} allowed_cidr=${ALLOWED_CIDR}"
echo "deploy: repo=${REPO_URL} ref=${REPO_REF}"

# --- 2. Terraform Init & Apply --------------------------------------- #
export TF_CLI_CONFIG_FILE="${TF_CLI_CONFIG_FILE:-/dev/null}"

echo "deploy: running terraform init..."
terraform -chdir="${TF_DIR}" init

echo "deploy: running terraform apply..."
terraform -chdir="${TF_DIR}" apply -auto-approve \
  -var="aws_region=${REGION}" \
  -var="instance_type=${INSTANCE_TYPE}" \
  -var="allowed_cidr=${ALLOWED_CIDR}" \
  -var="repo_url=${REPO_URL}" \
  -var="repo_ref=${REPO_REF}"

# --- 3. Extract Outputs ---------------------------------------------- #
PUBLIC_IP="$(terraform -chdir="${TF_DIR}" output -raw public_ip)"
PUBLIC_URL="$(terraform -chdir="${TF_DIR}" output -raw public_url)"
INSTANCE_ID="$(terraform -chdir="${TF_DIR}" output -raw instance_id)"
VPC_ID="$(terraform -chdir="${TF_DIR}" output -raw vpc_id)"
SUBNET_ID="$(terraform -chdir="${TF_DIR}" output -raw subnet_id)"

echo
echo "deploy: infrastructure provisioned successfully."
echo "  Instance ID: ${INSTANCE_ID}"
echo "  Public IP  : ${PUBLIC_IP}"
echo "  Public URL : ${PUBLIC_URL}"
echo "  VPC ID     : ${VPC_ID}"
echo "  Subnet ID  : ${SUBNET_ID}"
echo

if [ "${SKIP_HEALTH:-0}" = "1" ]; then
  echo "deploy: SKIP_HEALTH=1 — skipping external probe verification."
  exit 0
fi

# --- 4. External Health Gate ----------------------------------------- #
echo "deploy: waiting for application bootstrap and external reachability (up to 15 min)..."
deadline=$(( $(date +%s) + 900 ))
gate() { curl -fsS -o /dev/null --max-time 6 "$1"; }

for probe in \
  "http://${PUBLIC_IP}/healthz|nginx front-door" \
  "http://${PUBLIC_IP}/api/v1/health|backend liveness" \
  "http://${PUBLIC_IP}/api/v1/health/ready|backend readiness" \
  "http://${PUBLIC_IP}/|frontend SPA" ; do
  url="${probe%%|*}"
  name="${probe##*|}"
  until gate "${url}"; do
    if [ "$(date +%s)" -ge "${deadline}" ]; then
      echo "deploy: FAILED — ${name} not reachable at ${url}" >&2
      echo "deploy: check bootstrap logs using Session Manager:" >&2
      echo "  aws ssm start-session --target ${INSTANCE_ID} --region ${REGION}" >&2
      exit 1
    fi
    sleep 10
  done
  echo "deploy: OK  ${name}  (${url})"
done

# --- 5. Port Exposure Verification ----------------------------------- #
echo "deploy: verifying closed ports from outside the host..."
closed() { ! curl -s -o /dev/null --connect-timeout 4 "http://${PUBLIC_IP}:$1/" ; }

for p in 8000 5432 22; do
  if closed "${p}"; then
    echo "deploy: OK  port ${p} is closed / unreachable as required"
  else
    echo "deploy: FAILED — port ${p} is unexpectedly reachable from the internet!" >&2
    exit 1
  fi
done

echo
echo "=============================================================================="
echo "DEPLOYMENT COMPLETE & VERIFIED"
echo "=============================================================================="
echo "  Application URL : ${PUBLIC_URL}"
echo "  Session Manager : aws ssm start-session --target ${INSTANCE_ID} --region ${REGION}"
echo
echo "OPTIONAL GEMINI CONFIGURATION:"
echo "  To enable Gemini explanations without modifying Terraform or rebuilding images:"
echo "  1. Add /cryptiq/GEMINI_API_KEY as SecureString in AWS SSM Parameter Store."
echo "  2. Refresh the runtime by running:"
echo "     INSTANCE_ID=${INSTANCE_ID} AWS_REGION=${REGION} deploy/aws/scripts/refresh-secrets.sh"
echo
echo "TEARDOWN:"
echo "  deploy/aws/scripts/teardown.sh"
echo "=============================================================================="
