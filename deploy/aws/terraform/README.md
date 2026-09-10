# CRYPTIQ — Terraform AWS Deployment

This directory contains the authoritative, production-ready Terraform configuration for deploying CRYPTIQ to Amazon Web Services (AWS).

---

## 1. Architecture Overview

Designed specifically as a lightweight, reproducible, and cost-controlled deployment for hackathons and production pilots:

```
                      Internet
                         │ TCP 80 (only)
                         ▼
                  Internet Gateway
                         │
                  Route Table (0.0.0.0/0 -> IGW)
                         │
        ┌──────────────────────────────────────────────┐
        │  VPC 10.20.0.0/16 · Public Subnet 10.20.1.0/24 │
        ├──────────────────────────────────────────────┤
        │  EC2 t3.medium · Amazon Linux 2023           │
        │                                              │
        │  Nginx :80 (Reverse Proxy)                   │
        │    ├─ /      ──► Frontend:8080 (React SPA)   │
        │    └─ /api/  ──► Backend:8000  (FastAPI)     │
        │                                              │
        │  FastAPI + In-Process Scan Worker            │
        │                                              │
        │  SQLite ──► /data ──► Encrypted EBS (10 GiB) │
        └──────────────┬──────────────────┬────────────┘
                       │ container logs   │ cloud-init
                       ▼                  ▼
             CloudWatch Log Groups: /cryptiq/{backend,frontend,nginx,bootstrap}
```

### AWS Resources Managed by Terraform
- **VPC & Networking**: Dedicated VPC (`10.20.0.0/16`), public subnet (`10.20.1.0/24`), Internet Gateway, and public route table.
- **Security Group**: Strict ingress permitting **TCP port 80 only**. Ports 22 (SSH), 8000 (FastAPI), 5432, etc., are blocked externally.
- **Compute**: Single `t3.medium` EC2 instance running Amazon Linux 2023 with IMDSv2 enforced.
- **Storage**:
  - Encrypted root EBS volume (30 GiB gp3).
  - Dedicated encrypted persistent EBS volume (10 GiB gp3) mounted at `/data` for the SQLite database.
- **IAM**: Least-privilege instance role attaching `AmazonSSMManagedInstanceCore`, scoped CloudWatch logs access, and scoped `ssm:GetParameter` on `/cryptiq/*` with `kms:Decrypt` on `alias/aws/ssm`.
- **CloudWatch**: Dedicated log groups with 3-day retention for aggressive cost control.

---

## 2. Critical Secret Boundary

**No secret values ever exist in Terraform files, variables, or state.**

1. **Deployment without secrets**:
   - The infrastructure deploys cleanly whether `/cryptiq/GEMINI_API_KEY` exists or not.
   - When the parameter is absent, deterministic CRYPTIQ analysis and the Migration Advisor function normally. The AI explanation endpoint gracefully returns `HTTP 503 (AI_EXPLANATION_UNAVAILABLE)`.
2. **Operator manual provisioning**:
   - The operator creates `/cryptiq/GEMINI_API_KEY` manually as a `SecureString` in AWS Systems Manager Parameter Store.
3. **Dynamic secret activation**:
   - Running `deploy/aws/scripts/refresh-secrets.sh` (or SSM Run Command) retrieves the key into `/opt/cryptiq/.env` (mode `0600`) and restarts the backend container in-place.
   - **No Docker image rebuild** is needed and **no secrets are echoed or logged**.

---

## 3. Deployment Instructions

### Prerequisites
- [Terraform](https://www.terraform.io/) `>= 1.5.0`
- [AWS CLI](https://aws.amazon.com/cli/) configured with deployment credentials
- `curl`

### Steps

```bash
cd deploy/aws/terraform

# 1. Initialize provider plugins
terraform init

# 2. Plan the deployment
terraform plan

# 3. Apply the infrastructure
terraform apply
```

Outputs will display:
```text
public_ip           = "x.x.x.x"
public_url          = "http://x.x.x.x/"
instance_id         = "i-xxxxxxxxxxxxxxxxx"
ssm_session_command = "aws ssm start-session --target i-xxxxxxxxxxxxxxxxx --region us-east-1"
```

---

## 4. Activating Gemini Explanations (Manual Step)

Once the stack is provisioned, you can optionally configure Gemini AI explanations at any time:

### Step 1: Create the Parameter in AWS
Via AWS Management Console:
1. Open **AWS Systems Manager** -> **Parameter Store**.
2. Click **Create parameter**.
3. Set **Name**: `/cryptiq/GEMINI_API_KEY`
4. Set **Type**: `SecureString`
5. Set **KMS Key source**: `My current account` (uses default `alias/aws/ssm`)
6. Paste your Gemini API key in **Value**.
7. Click **Create parameter**.

Or via AWS CLI:
```bash
aws ssm put-parameter \
  --name "/cryptiq/GEMINI_API_KEY" \
  --type "SecureString" \
  --value "YOUR_KEY_HERE" \
  --overwrite
```

### Step 2: Refresh the Runtime Environment
Run the safe refresh script without rebuilding images:

```bash
# From your local machine:
INSTANCE_ID=<instance-id> AWS_REGION=us-east-1 deploy/aws/scripts/refresh-secrets.sh

# Or directly on the EC2 instance via Session Manager:
aws ssm start-session --target <instance-id> --region us-east-1
bash /opt/cryptiq/app/deploy/aws/scripts/refresh-secrets.sh
```

---

## 5. Health & Verification Probes

Verify the deployed endpoints:

```bash
# Nginx front-door liveness
curl -fsS http://<public-ip>/healthz

# Backend application liveness
curl -fsS http://<public-ip>/api/v1/health

# Backend database readiness
curl -fsS http://<public-ip>/api/v1/health/ready

# Frontend SPA root
curl -fsS http://<public-ip>/
```

Verify closed external ports:
```bash
curl --connect-timeout 4 http://<public-ip>:22/    # Must time out / be blocked
curl --connect-timeout 4 http://<public-ip>:8000/  # Must time out / be blocked
```

---

## 6. Teardown

To destroy all billable AWS resources created by Terraform:

```bash
cd deploy/aws/terraform
terraform destroy -auto-approve
```

---

## 7. Cost Optimization Breakdown

| Resource | Configuration | Estimated Cost |
|---|---|---|
| EC2 | 1× `t3.medium` (2 vCPU, 4 GiB RAM) | ~$0.0416 / hour (~$1.00 / day) |
| Root EBS | 30 GiB gp3 encrypted | ~$0.08 / day |
| Data EBS | 10 GiB gp3 encrypted | ~$0.03 / day |
| Networking | VPC, Subnet, IGW, Route Table | $0.00 (no NAT Gateway, no ALB) |
| CloudWatch | 4 log groups, 3-day retention | < $0.05 / day |
| **Total** | **Minimal single-instance footprint** | **~$1.15 / day** |
