# ==============================================================================
# SSM PARAMETER STORE — SECRET ARCHITECTURAL BOUNDARY
# ==============================================================================
#
# CRITICAL SECURITY DESIGN:
#
# The Gemini API key is an operator-supplied secret. Terraform intentionally does
# NOT define or manage the `aws_ssm_parameter` resource value for
# `/cryptiq/GEMINI_API_KEY`, because doing so would risk writing secret values
# into the Terraform state file, .tfvars, or version control.
#
# Boundary definition:
# 1. Terraform provisions:
#    - IAM policy granting ssm:GetParameter/ssm:GetParameters on /cryptiq/*
#    - IAM policy granting kms:Decrypt on alias/aws/ssm
#    - EC2 user_data and runtime scripts referencing the parameter name
#
# 2. Operator manually provisions (via AWS Console or AWS CLI):
#    - Name:  /cryptiq/GEMINI_API_KEY
#    - Type:  SecureString
#    - Value: <User's private Gemini API key>
#
# 3. Graceful degradation:
#    - If absent: CRYPTIQ deterministic engine runs fully; AI explanation
#      gracefully returns HTTP 503 (AI_EXPLANATION_UNAVAILABLE).
#    - If present: backend retrieves via IAM at runtime into /opt/cryptiq/.env,
#      enabling Gemini without image rebuilds or Terraform state modification.
# ==============================================================================

locals {
  # Authoritative parameter path consumed by CRYPTIQ runtime
  gemini_parameter_path = "/cryptiq/GEMINI_API_KEY"
}
