# Cryptiq — AWS Deployment

This directory contains the deployment infrastructure for CRYPTIQ on Amazon Web Services (AWS).

> **DEPLOYMENT STATUS:**
> - **PRIMARY / AUTHORITATIVE:** **Terraform** (`deploy/aws/terraform/`)
> - **LEGACY / DEPRECATED:** **CloudFormation** (`deploy/aws/cloudformation/`) retained for historical reference only.

---

## 1. Target Architecture

CRYPTIQ runs as a single-instance, cost-optimized, secure demonstration stack:

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

    Operator access : SSM Session Manager (no SSH, no key pair, port 22 closed)
    Secrets         : SSM Parameter Store SecureString → instance role → /opt/cryptiq/.env
```

### Key Architectural Properties
* **Port Isolation**: External security group permits ONLY **TCP port 80**. Container ports 8000 (FastAPI), 8080 (Frontend), and host port 22 (SSH) are blocked externally.
* **Single-Origin Routing**: Nginx routes `/` to the React frontend and `/api/` to the FastAPI backend. The frontend uses a relative `/api/v1` base URL, avoiding CORS.
* **Storage Persistence**: SQLite database resides at `/data/cryptiq.db` on a dedicated, encrypted `gp3` EBS volume (mounted at `/data`). Findings survive container restarts.
* **Strict Least-Privilege IAM**: Managed via Session Manager (`AmazonSSMManagedInstanceCore`), with scoped CloudWatch log write permissions and scoped SSM read/decrypt on `/cryptiq/*`.
* **Zero Secrets in State**: The Gemini API key is never placed in Terraform configuration, `.tfvars`, or Terraform state.

---

## 2. Directory Structure

```text
deploy/aws/
├── terraform/               # PRIMARY: Authoritative Terraform configuration
│   ├── versions.tf          # Terraform and AWS provider versions
│   ├── providers.tf         # AWS provider and default resource tags
│   ├── variables.tf         # Parameterized deployment variables
│   ├── locals.tf            # Naming, tagging, and log group locals
│   ├── network.tf           # VPC, Internet Gateway, Subnet, Route Table
│   ├── security.tf          # Security group (TCP 80 only)
│   ├── iam.tf               # Least-privilege EC2 role, profile, and policies
│   ├── ssm.tf               # SSM parameter architectural boundary documentation
│   ├── cloudwatch.tf        # CloudWatch log groups with 3-day retention
│   ├── ec2.tf               # t3.medium instance, IMDSv2, EBS volumes
│   ├── outputs.tf           # Public URL, IP, instance ID, SSM commands
│   ├── user_data.sh.tftpl   # EC2 bootstrap script template
│   ├── terraform.tfvars.example
│   ├── .gitignore
│   └── README.md            # Detailed Terraform documentation
├── scripts/
│   ├── deploy.sh            # Automated Terraform deployment & health verification
│   ├── teardown.sh          # Automated Terraform destroy & cleanup
│   ├── setup.sh             # Safely store Gemini API key in SSM Parameter Store
│   └── refresh-secrets.sh   # Safely reload SSM secrets and restart backend
├── compose/
│   ├── docker-compose.aws.yml # Production multi-container composition
│   └── nginx.conf           # Single-origin reverse proxy configuration
├── cloudwatch/
│   └── README.md            # Log group definitions and event structure
├── iam/
│   └── instance-role-policy.json # Reference IAM policy for review
└── cloudformation/          # LEGACY: Deprecated CloudFormation template
    └── cryptiq-demo.yaml
```

---

## 3. Quick Start (Primary Workflow)

### Deploying Infrastructure

```bash
cd deploy/aws/terraform

# 1. Initialize
terraform init

# 2. Review execution plan
terraform plan

# 3. Apply
terraform apply
```

Alternatively, use the convenience wrapper script:
```bash
deploy/aws/scripts/deploy.sh
```

### Connecting to the Host
Administration is done strictly via **AWS Systems Manager Session Manager** (no SSH keys or port 22):
```bash
aws ssm start-session --target <instance-id> --region us-east-1
```

---

## 4. Gemini API Key Configuration (Zero-Secret Workflow)

The deployment functions completely whether the Gemini key is present or absent:
- **Without Key**: Deterministic scanning, static analysis, and Context-Aware Migration Advisor run at 100% functionality. The AI explanation endpoint gracefully reports `HTTP 503 (AI_EXPLANATION_UNAVAILABLE)`.
- **With Key**: AI explanations activate dynamically.

### Adding the Secret Manually in AWS
1. Navigate to **AWS Systems Manager** → **Parameter Store**.
2. Click **Create parameter**.
3. Configure:
   - **Name**: `/cryptiq/GEMINI_API_KEY`
   - **Type**: `SecureString`
   - **KMS Key source**: `My current account` (`alias/aws/ssm`)
   - **Value**: `<your-api-key>`
4. Click **Create parameter**.

Or run the interactive prompt helper:
```bash
deploy/aws/scripts/setup.sh
```

### Dynamically Refreshing the Runtime
To activate the key without rebuilding images or modifying Terraform state:
```bash
# From operator laptop:
INSTANCE_ID=<instance-id> AWS_REGION=us-east-1 deploy/aws/scripts/refresh-secrets.sh

# Or directly on EC2 via SSM Session:
bash /opt/cryptiq/app/deploy/aws/scripts/refresh-secrets.sh
```

---

## 5. Health Verification Probes

```bash
# Nginx reverse proxy
curl -fsS http://<public-ip>/healthz

# Backend application liveness
curl -fsS http://<public-ip>/api/v1/health

# Backend database readiness
curl -fsS http://<public-ip>/api/v1/health/ready

# Frontend SPA
curl -fsS http://<public-ip>/

# Verify closed ports (must time out / reject)
curl --connect-timeout 4 http://<public-ip>:22/
curl --connect-timeout 4 http://<public-ip>:8000/
```

---

## 6. Teardown

```bash
cd deploy/aws/terraform
terraform destroy -auto-approve
```
Or via script:
```bash
deploy/aws/scripts/teardown.sh
```

---

## 7. Cost Breakdown (Hackathon Demo Footprint)

| Resource | Size / Spec | Estimated Cost |
|---|---|---|
| EC2 | 1× `t3.medium` | ~$0.0416 / hr (~$1.00 / day) |
| Root Storage | 30 GiB gp3 encrypted | ~$0.08 / day |
| Data Storage | 10 GiB gp3 encrypted | ~$0.03 / day |
| Networking | VPC, Subnet, IGW (no NAT GW, no ALB) | Free |
| CloudWatch | 4 log groups (3-day retention) | < $0.05 / day |
| **Total** | **Minimal single-node demo** | **~$1.15 / day** |
