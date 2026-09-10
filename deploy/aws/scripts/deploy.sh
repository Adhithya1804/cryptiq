#!/usr/bin/env bash
# Create (or update) the Cryptiq demo stack and prove it is externally reachable.
#
#   REPO_URL=https://github.com/<you>/<repo>.git \
#   REPO_REF=v1.2.3 \
#   deploy/aws/scripts/deploy.sh
#
# Optional env:
#   STACK_NAME     (default cryptiq-demo)
#   AWS_REGION     (default us-east-1)
#   VPC_ID         (default: the account's default VPC)
#   SUBNET_ID      (default: first public subnet of that VPC)
#   INSTANCE_TYPE  (default t3.medium)
#   ALLOWED_CIDR   (default 0.0.0.0/0)
#   SKIP_HEALTH    (set to 1 to create the stack but not block on external health)
#
# Exits non-zero if a prerequisite is missing, if AWS credentials are invalid,
# if the stack fails, OR if the external health / port-exposure checks fail.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${HERE}/../cloudformation/cryptiq-demo.yaml"
STACK_NAME="${STACK_NAME:-cryptiq-demo}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
ALLOWED_CIDR="${ALLOWED_CIDR:-0.0.0.0/0}"
REPO_REF="${REPO_REF:-main}"

aws() { command aws --region "${REGION}" "$@"; }

die() { echo "deploy: $*" >&2; exit 2; }

# --- 1. Prerequisites --------------------------------------------------- #
for bin in aws curl; do
  command -v "${bin}" >/dev/null 2>&1 || die "'${bin}' not found on PATH"
done
[ -f "${TEMPLATE}" ] || die "template not found: ${TEMPLATE}"
[ -n "${REPO_URL:-}" ] || die "set REPO_URL to the public git URL of this repository"
case "${ALLOWED_CIDR}" in
  */[0-9]|*/[0-9][0-9]) : ;;
  *) die "ALLOWED_CIDR must look like 1.2.3.4/32 (got '${ALLOWED_CIDR}')" ;;
esac

cli_major="$(command aws --version 2>&1 | sed -n 's#^aws-cli/\([0-9]\).*#\1#p')"
[ "${cli_major:-0}" -ge 2 ] 2>/dev/null || echo "deploy: WARNING aws-cli v2 recommended (found: $(command aws --version 2>&1))"

# --- 2. AWS authentication ------------------------------------------- #
# Do this BEFORE anything else touches AWS so an expired / wrong / missing
# credential fails here with a clear message instead of a confusing
# InvalidClientTokenId from a describe call five steps later.
echo "deploy: checking AWS credentials (aws sts get-caller-identity, region ${REGION})..."
err_file="$(mktemp "${TMPDIR:-/tmp}/cryptiq-deploy.XXXXXX")"
trap 'rm -f "${err_file}"' EXIT
if ! caller="$(aws sts get-caller-identity --output json 2>"${err_file}")"; then
  echo "deploy: FAILED — AWS credentials are not valid for region ${REGION}." >&2
  sed 's/^/  /' "${err_file}" >&2 || true
  cat >&2 <<'EOF'

  Fix one of:
    * export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN
    * aws configure   (or:  aws configure --profile <name> && export AWS_PROFILE=<name>)
    * aws sso login --profile <name>
  Then re-run this script. Nothing was created.
EOF
  exit 3
fi
account="$(printf '%s' "${caller}" | sed -n 's/.*"Account"[: ]*"\([0-9]*\)".*/\1/p')"
arn="$(printf '%s' "${caller}" | sed -n 's/.*"Arn"[: ]*"\([^"]*\)".*/\1/p')"
echo "deploy: authenticated — account ${account:-?} as ${arn:-?}"

# --- 3. Resolve VPC / subnet --------------------------------------- #
VPC_ID="${VPC_ID:-$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)}"
if [ "${VPC_ID}" = "None" ] || [ -z "${VPC_ID}" ]; then
  die "no default VPC in ${REGION}; set VPC_ID and SUBNET_ID"
fi

if [ -z "${SUBNET_ID:-}" ]; then
  SUBNET_ID="$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=${VPC_ID}" "Name=map-public-ip-on-launch,Values=true" \
    --query 'Subnets[0].SubnetId' --output text)"
fi
if [ "${SUBNET_ID}" = "None" ] || [ -z "${SUBNET_ID}" ]; then
  die "no public subnet in ${VPC_ID}; set SUBNET_ID"
fi

echo "deploy: stack=${STACK_NAME} region=${REGION} vpc=${VPC_ID} subnet=${SUBNET_ID}"
echo "deploy: repo=${REPO_URL}@${REPO_REF} instance=${INSTANCE_TYPE} cidr=${ALLOWED_CIDR}"

# --- 4. Deploy ---------------------------------------------------- #
# On failure, dump the stack events so the reason is visible without a
# second console round-trip.
dump_events() {
  echo "deploy: --- recent CloudFormation events for ${STACK_NAME} ---" >&2
  aws cloudformation describe-stack-events --stack-name "${STACK_NAME}" \
    --query 'reverse(StackEvents[?ResourceStatusReason!=`null`])[:25].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
    --output text 2>/dev/null | sed 's/^/  /' >&2 || true
}
trap 'rc=$?; [ "${rc}" -ne 0 ] && dump_events; exit "${rc}"' ERR

aws cloudformation deploy \
  --stack-name "${STACK_NAME}" \
  --template-file "${TEMPLATE}" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    VpcId="${VPC_ID}" \
    SubnetId="${SUBNET_ID}" \
    InstanceType="${INSTANCE_TYPE}" \
    RepoUrl="${REPO_URL}" \
    RepoRef="${REPO_REF}" \
    AllowedCidr="${ALLOWED_CIDR}"

trap - ERR

PUBLIC_IP="$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicIp'].OutputValue" --output text)"
INSTANCE_ID="$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)"
echo "deploy: instance ${INSTANCE_ID} at ${PUBLIC_IP}"

if [ "${SKIP_HEALTH:-0}" = "1" ]; then
  echo "deploy: SKIP_HEALTH=1 — stack created, not waiting for the app."
  echo "  URL     : http://${PUBLIC_IP}/"
  echo "  shell   : aws ssm start-session --target ${INSTANCE_ID} --region ${REGION}"
  echo "  logs    : aws logs tail /cryptiq/bootstrap --follow --region ${REGION}"
  exit 0
fi

# --- 5. External health gate ------------------------------------- #
# The instance still has to run user-data.sh (Docker build + compose up). Poll
# the public IP from HERE (outside the host) so we prove real reachability.
echo "deploy: waiting for http://${PUBLIC_IP}/ to serve (build can take a few minutes)..."
deadline=$(( $(date +%s) + 900 ))
gate() { curl -fsS -o /dev/null --max-time 6 "$1"; }
for probe in \
  "http://${PUBLIC_IP}/healthz|nginx" \
  "http://${PUBLIC_IP}/api/v1/health|backend liveness" \
  "http://${PUBLIC_IP}/api/v1/health/ready|backend readiness" \
  "http://${PUBLIC_IP}/|frontend" ; do
  url="${probe%%|*}"; name="${probe##*|}"
  until gate "${url}"; do
    if [ "$(date +%s)" -ge "${deadline}" ]; then
      echo "deploy: FAILED — ${name} not reachable at ${url}" >&2
      echo "deploy: inspect the boot log with:" >&2
      echo "  aws logs tail /cryptiq/bootstrap --since 15m --region ${REGION}" >&2
      echo "  aws ssm start-session --target ${INSTANCE_ID} --region ${REGION}" >&2
      exit 1
    fi
    sleep 10
  done
  echo "deploy: OK  ${name}  ${url}"
done

# --- 6. Port exposure check ------------------------------------ #
echo "deploy: verifying port exposure from outside the host..."
closed() { ! curl -s -o /dev/null --connect-timeout 4 "http://${PUBLIC_IP}:$1/" ; }
for p in 8000 5432 22; do
  if closed "${p}"; then echo "deploy: OK  port ${p} not reachable"; else
    echo "deploy: FAILED — port ${p} is reachable from the internet" >&2; exit 1; fi
done

echo
echo "deploy: SUCCESS"
echo "  URL     : http://${PUBLIC_IP}/"
echo "  shell   : aws ssm start-session --target ${INSTANCE_ID} --region ${REGION}"
echo "  logs    : aws logs tail /cryptiq/backend --follow --region ${REGION}"
echo "  teardown: STACK_NAME=${STACK_NAME} AWS_REGION=${REGION} deploy/aws/scripts/teardown.sh"
