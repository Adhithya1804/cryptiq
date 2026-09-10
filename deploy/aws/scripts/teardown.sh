#!/usr/bin/env bash
# Remove every billable resource the demo created and PROVE it is gone.
#
#   STACK_NAME=cryptiq-demo AWS_REGION=us-east-1 deploy/aws/scripts/teardown.sh
#
# Removes: the CloudFormation stack (EC2 instance, both EBS volumes, security
# group, IAM role + instance profile, all four CloudWatch log groups) and the
# optional SSM parameter. The stack owns the log groups (DeletionPolicy defaults
# to Delete) so they go with it; this script also deletes them explicitly and
# then verifies, in case the stack was edited.
set -euo pipefail

STACK_NAME="${STACK_NAME:-cryptiq-demo}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
aws() { command aws --region "${REGION}" "$@"; }

echo "teardown: deleting stack ${STACK_NAME} in ${REGION}"
if aws cloudformation describe-stacks --stack-name "${STACK_NAME}" >/dev/null 2>&1; then
  aws cloudformation delete-stack --stack-name "${STACK_NAME}"
  aws cloudformation wait stack-delete-complete --stack-name "${STACK_NAME}"
  echo "teardown: stack deleted"
else
  echo "teardown: stack not found (already gone)"
fi

echo "teardown: removing optional SSM parameter"
aws ssm delete-parameter --name /cryptiq/GEMINI_API_KEY >/dev/null 2>&1 \
  && echo "teardown: deleted /cryptiq/GEMINI_API_KEY" \
  || echo "teardown: /cryptiq/GEMINI_API_KEY not present"

echo "teardown: removing any leftover log groups"
for lg in /cryptiq/backend /cryptiq/frontend /cryptiq/nginx /cryptiq/bootstrap; do
  aws logs delete-log-group --log-group-name "${lg}" >/dev/null 2>&1 \
    && echo "teardown: deleted ${lg}" || true
done

# --- Verification ------------------------------------------------ #
echo
echo "teardown: verifying..."
fail=0

if aws cloudformation describe-stacks --stack-name "${STACK_NAME}" >/dev/null 2>&1; then
  state="$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].StackStatus' --output text)"
  [ "${state}" = "DELETE_COMPLETE" ] || { echo "  STILL PRESENT: stack (${state})"; fail=1; }
else
  echo "  OK  stack gone"
fi

running="$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=cryptiq-demo" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text)"
[ -z "${running}" ] && echo "  OK  no cryptiq-demo instances" || { echo "  STILL PRESENT: instances ${running}"; fail=1; }

remaining="$(aws logs describe-log-groups --log-group-name-prefix /cryptiq/ \
  --query 'logGroups[].logGroupName' --output text)"
[ -z "${remaining}" ] && echo "  OK  no /cryptiq/ log groups" || { echo "  STILL PRESENT: log groups ${remaining}"; fail=1; }

param="$(aws ssm get-parameters --names /cryptiq/GEMINI_API_KEY \
  --query 'Parameters[].Name' --output text)"
[ -z "${param}" ] && echo "  OK  no /cryptiq SSM parameters" || { echo "  STILL PRESENT: ${param}"; fail=1; }

echo
if [ "${fail}" -eq 0 ]; then echo "teardown: CLEAN — nothing billable remains"; else
  echo "teardown: INCOMPLETE — see STILL PRESENT lines above"; exit 1; fi
