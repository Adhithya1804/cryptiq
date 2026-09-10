#!/usr/bin/env bash
# Remove every billable resource the demo created and PROVE it is gone.
#
#   STACK_NAME=cryptiq-demo AWS_REGION=us-east-1 deploy/aws/scripts/teardown.sh
#
# Removes: the CloudFormation stack (EC2 instance, both EBS volumes, security
# group, IAM role + instance profile, all four CloudWatch log groups, and — when
# this stack created them — the VPC, public subnet, Internet Gateway and route
# table) plus the optional SSM parameter. The stack owns those resources
# (DeletionPolicy defaults to Delete) so they go with it; this script also
# deletes the log groups explicitly and, if the stack-created VPC somehow
# survives, removes the leftover networking, then verifies everything.
#
# SAFETY: networking is only ever touched when the stack's own CreatedNetwork
# output is "true". A VPC/subnet supplied through VPC_ID/SUBNET_ID has
# CreatedNetwork="false" and is never modified or deleted.
set -euo pipefail

STACK_NAME="${STACK_NAME:-cryptiq-demo}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
aws() { command aws --region "${REGION}" "$@"; }

# --- Read what the stack says about its networking BEFORE deleting it --- #
created_net=""
stack_vpc=""
if aws cloudformation describe-stacks --stack-name "${STACK_NAME}" >/dev/null 2>&1; then
  created_net="$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='CreatedNetwork'].OutputValue" --output text 2>/dev/null || true)"
  stack_vpc="$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='VpcId'].OutputValue" --output text 2>/dev/null || true)"
fi
[ "${created_net}" = "true" ] \
  && echo "teardown: this stack created VPC ${stack_vpc} — it will be removed" \
  || echo "teardown: networking was pre-existing or unknown — it will NOT be touched"

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

# --- Temporary networking: only if THIS stack created it --------------- #
# CloudFormation removes the VPC/subnet/IGW/route table with the stack. This is
# a targeted safety net scoped strictly to the VPC id from the stack's own
# CreatedNetwork/VpcId outputs, in case the stack was interrupted or edited.
if [ "${created_net}" = "true" ] && [ -n "${stack_vpc}" ] && [ "${stack_vpc}" != "None" ]; then
  if aws ec2 describe-vpcs --vpc-ids "${stack_vpc}" >/dev/null 2>&1; then
    echo "teardown: stack-created VPC ${stack_vpc} still present — removing leftover networking"
    for eni in $(aws ec2 describe-network-interfaces \
      --filters "Name=vpc-id,Values=${stack_vpc}" \
      --query 'NetworkInterfaces[?Status==`available`].NetworkInterfaceId' --output text 2>/dev/null || true); do
      aws ec2 delete-network-interface --network-interface-id "${eni}" 2>/dev/null \
        && echo "  deleted eni ${eni}" || true
    done
    for sn in $(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${stack_vpc}" \
      --query 'Subnets[].SubnetId' --output text 2>/dev/null || true); do
      aws ec2 delete-subnet --subnet-id "${sn}" 2>/dev/null && echo "  deleted subnet ${sn}" || true
    done
    for igw in $(aws ec2 describe-internet-gateways \
      --filters "Name=attachment.vpc-id,Values=${stack_vpc}" \
      --query 'InternetGateways[].InternetGatewayId' --output text 2>/dev/null || true); do
      aws ec2 detach-internet-gateway --internet-gateway-id "${igw}" --vpc-id "${stack_vpc}" 2>/dev/null || true
      aws ec2 delete-internet-gateway --internet-gateway-id "${igw}" 2>/dev/null \
        && echo "  deleted igw ${igw}" || true
    done
    for rt in $(aws ec2 describe-route-tables --filters "Name=vpc-id,Values=${stack_vpc}" \
      --query 'RouteTables[?length(Associations[?Main]) == `0`].RouteTableId' --output text 2>/dev/null || true); do
      aws ec2 delete-route-table --route-table-id "${rt}" 2>/dev/null \
        && echo "  deleted route table ${rt}" || true
    done
    aws ec2 delete-vpc --vpc-id "${stack_vpc}" 2>/dev/null && echo "  deleted vpc ${stack_vpc}" || true
  fi
fi

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
# Both EBS volumes are DeleteOnTermination:true, so they go with the instance.

remaining="$(aws logs describe-log-groups --log-group-name-prefix /cryptiq/ \
  --query 'logGroups[].logGroupName' --output text)"
[ -z "${remaining}" ] && echo "  OK  no /cryptiq/ log groups" || { echo "  STILL PRESENT: log groups ${remaining}"; fail=1; }

param="$(aws ssm get-parameters --names /cryptiq/GEMINI_API_KEY \
  --query 'Parameters[].Name' --output text)"
[ -z "${param}" ] && echo "  OK  no /cryptiq SSM parameters" || { echo "  STILL PRESENT: ${param}"; fail=1; }

if [ "${created_net}" = "true" ] && [ -n "${stack_vpc}" ] && [ "${stack_vpc}" != "None" ]; then
  if aws ec2 describe-vpcs --vpc-ids "${stack_vpc}" >/dev/null 2>&1; then
    echo "  STILL PRESENT: stack-created VPC ${stack_vpc}"; fail=1
  else
    echo "  OK  stack-created VPC ${stack_vpc} gone"
  fi
elif [ "${created_net}" = "false" ]; then
  echo "  OK  networking was pre-existing (VPC_ID/SUBNET_ID) — left untouched"
fi

echo
if [ "${fail}" -eq 0 ]; then echo "teardown: CLEAN — nothing billable remains"; else
  echo "teardown: INCOMPLETE — see STILL PRESENT lines above"; exit 1; fi
