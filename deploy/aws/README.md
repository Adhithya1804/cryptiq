# Cryptiq — AWS hackathon deployment

A **temporary, single-instance** deployment of the existing Docker Compose
stack. Not a production SaaS architecture — no Route 53, ALB, RDS, ECS/EKS,
NAT Gateway, autoscaling, or multi-region. One EC2 instance, one public port.

It deploys into a **clean AWS account with no VPC**: by default the stack
creates the minimal networking it needs (`CreateNetwork=true`). If you already
have networking, set `CreateNetwork=false` and pass `VPC_ID` / `SUBNET_ID`.

```
                       Internet
                          │  TCP 80 (only)
                          ▼
                   Internet Gateway
                          │
                   public route table  (0.0.0.0/0 → IGW)
                          │
        ┌─────────────────────────────────────────┐
        │  VPC 10.20.0.0/16 · public subnet        │  ← created by the stack
        │  (CreateNetwork=true), or your own       │     when CreateNetwork=true
        ├─────────────────────────────────────────┤
        │  EC2 t3.medium · Amazon Linux 2023       │
        │                                         │
        │  nginx :80 (container)                   │
        │    ├─ /      → frontend:8080  (React SPA)│
        │    └─ /api/  → backend:8000   (FastAPI)  │
        │                                         │
        │  FastAPI + in-process scan worker       │
        │                                         │
        │  SQLite  ──►  /data  ──►  encrypted EBS  │
        └───────┬───────────────────┬─────────────┘
                │ container stdout  │ /var/log/cloud-init-output.log
                ▼ (awslogs driver)  ▼ (CloudWatch agent)
        CloudWatch Logs: /cryptiq/{backend,frontend,nginx,bootstrap}  (3-day retention)

   Operator access : SSM Session Manager      (no SSH, no key pair, port 22 closed)
   Secrets         : SSM Parameter Store SecureString  →  instance role  →  /opt/cryptiq/.env
```

The backend and frontend container ports are **never published to the host**;
`8000` / `5432` / `22` are not in the security group. Only `80` is open
(`0.0.0.0/0` by default — narrow it with `ALLOWED_CIDR`).

## Files

| Path | Purpose |
|---|---|
| `cloudformation/cryptiq-demo.yaml` | The whole stack: (optional) VPC + public subnet + Internet Gateway + route table, EC2, 2× encrypted EBS, security group, IAM role + instance profile, 4 CloudWatch log groups. `CreateNetwork=true` (default) builds the networking; `CreateNetwork=false` consumes `VpcId`/`SubnetId`. `cfn-lint` clean. |
| `user-data.sh` | First-boot bootstrap: Docker + Compose plugin + CloudWatch agent, mount the data volume, pull secrets from SSM, `compose up`, health-gate. |
| `compose/docker-compose.aws.yml` | Standalone Compose stack: adds the public `nginx :80`, drops all other published ports, builds the frontend with `VITE_API_BASE_URL=/api/v1`, runs the backend `production` profile, ships logs via `awslogs`. |
| `compose/nginx.conf` | The `:80` reverse proxy. `client_max_body_size 1m`. |
| `cloudwatch/README.md` | Log-group layout, the events emitted, the "no secret leaked" check. |
| `iam/instance-role-policy.json` | Review copy of the least-privilege inline policy. |
| `scripts/setup.sh` | Put the optional `GEMINI_API_KEY` into SSM (SecureString). |
| `scripts/deploy.sh` | Preflight (`aws`/`curl`/template present, `aws sts get-caller-identity`, VPC/subnet resolve) → `cloudformation deploy --no-fail-on-empty-changeset` → **external** health + port-exposure checks. Dumps stack events on failure. Fails loudly with distinct exit codes. |
| `scripts/teardown.sh` | Delete everything billable and **verify** it is gone. |

## Prerequisites

* **AWS CLI v2** on `PATH`, plus `curl`. `deploy.sh` checks both and the
  template file before it touches AWS.
* **Valid credentials.** `deploy.sh` runs `aws sts get-caller-identity` first
  and stops with exit code `3` and a remediation list if they are missing or
  expired — nothing is created. Set them with `aws configure`, `AWS_PROFILE`,
  `aws sso login`, or the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
  environment variables.
* **A standard region.** Opt-in regions that the account has not enabled
  (e.g. `ap-south-2`) reject every call with `InvalidClientTokenId` even when
  the credentials are fine. Pass `AWS_REGION=us-east-1` (or another enabled
  region) if your CLI default is an opt-in region.
* **This repository pushed to a public git URL**, with `deploy/aws/` committed.
  The instance `git clone`s `REPO_URL` at `REPO_REF` on first boot and runs
  `deploy/aws/user-data.sh` from the clone — uncommitted local changes are not
  deployed. A private repo would need a baked AMI (out of scope).
* **Networking — nothing required.** By default (`CREATE_NETWORK=true`) the
  stack creates a minimal VPC (`10.20.0.0/16`), one public subnet
  (`10.20.1.0/24`), an Internet Gateway and a route table — no NAT Gateway.
  This is the reproducible path and works on an account with **no VPC at all**.
  To reuse existing networking instead, set `CREATE_NETWORK=false` and pass
  `VPC_ID` + `SUBNET_ID` (a public subnet); `deploy.sh` will also fall back to
  the account's default VPC in that mode. A pre-existing VPC passed this way is
  never modified or deleted by `teardown.sh`.

## Deploy

```bash
# 1. (optional) store the Gemini key — skip entirely to run without AI explanations
GEMINI_API_KEY=... deploy/aws/scripts/setup.sh

# 2a. MODE 1 — clean account, stack builds the VPC/subnet/IGW (default)
REPO_URL=https://github.com/<you>/<repo>.git \
REPO_REF=<tag-or-branch> \
AWS_REGION=us-east-1 \
deploy/aws/scripts/deploy.sh

# 2b. MODE 2 — reuse existing networking
REPO_URL=... REPO_REF=... AWS_REGION=us-east-1 \
CREATE_NETWORK=false VPC_ID=vpc-xxxx SUBNET_ID=subnet-xxxx \
deploy/aws/scripts/deploy.sh
```

`CREATE_NETWORK` defaults to `true`. In that mode `VPC_ID`/`SUBNET_ID` must be
unset — the stack owns the networking and `teardown.sh` removes it. In
`CREATE_NETWORK=false` mode the networking you supply (or the account default
VPC) is used as-is and left untouched on teardown.

`deploy.sh` prints the public URL, the SSM session command, and the log-tail
command on success. Exit codes:

| Code | Meaning |
|---|---|
| `2` | Missing prerequisite (`aws`/`curl`/template), no `REPO_URL`, bad `ALLOWED_CIDR`/`CREATE_NETWORK`, or `CREATE_NETWORK=false` with no usable VPC/subnet — nothing created. |
| `3` | `aws sts get-caller-identity` failed — credentials missing/expired/wrong region. Nothing created. |
| `1` | Stack created but `http://<ip>/healthz`, `/api/v1/health`, `/api/v1/health/ready`, or `/` never came up, or `8000/5432/22` were reachable from outside. On a CloudFormation failure the last 25 stack events are printed. |

It is safe to re-run: `cloudformation deploy --no-fail-on-empty-changeset`
updates the stack in place, and a no-op re-run exits `0`. Set `SKIP_HEALTH=1`
to create/update the stack without blocking on the external health gate.

## Operate

```bash
aws ssm start-session --target <instance-id> --region <region>   # shell, no SSH
aws logs tail /cryptiq/backend --follow --region <region>        # live app logs
```

Inside the instance, the app lives at `/opt/cryptiq/app`:

```bash
cd /opt/cryptiq/app
docker compose -f deploy/aws/compose/docker-compose.aws.yml ps
docker compose -f deploy/aws/compose/docker-compose.aws.yml restart backend
```

## Persistence

SQLite is a bind mount to `/data`, backed by a dedicated encrypted EBS volume
(`/dev/sdf`, `mkfs.xfs` on first boot, `nofail` in `/etc/fstab`). Findings
survive:

* `docker compose restart backend` — volume is untouched;
* `docker compose down && up` — bind mount, not a named volume;
* instance stop/start — the EBS volume persists.

They do **not** survive `teardown.sh` (the volume has `DeleteOnTermination:
true` — this is a throwaway demo).

## Cost (us-east-1, on-demand, approximate)

| Resource | Rate | 2-hour demo | Full day |
|---|---|---|---|
| EC2 t3.medium | $0.0416/hr | ~$0.09 | ~$1.00 |
| EBS gp3 30 + 10 GiB | $0.08/GiB-mo | ~$0.01 | ~$0.11 |
| CloudWatch Logs (few MB, 3-day) | $0.50/GB ingest | <$0.01 | <$0.01 |
| Data transfer out (demo traffic) | $0.09/GB | <$0.05 | <$0.20 |
| **Total** | | **≈ $0.15** | **≈ $1.35** |

No NAT Gateway, no ALB, no Elastic IP, no RDS. A VPC, subnet, Internet Gateway
and route table are free. Comfortably inside ~$100 of credits. The only thing
that runs up a bill is forgetting to tear down — so:

## Teardown

```bash
AWS_REGION=us-east-1 deploy/aws/scripts/teardown.sh
```

Deletes the stack (EC2, both EBS volumes, security group, IAM role + instance
profile, all four log groups, **and — when `CreatedNetwork=true` — the VPC,
public subnet, Internet Gateway and route table this stack created**) plus the
`/cryptiq/GEMINI_API_KEY` parameter, then verifies: stack `DELETE_COMPLETE`, no
`cryptiq-demo` instances, no `/cryptiq/` log groups, no `/cryptiq/` SSM
parameters, and the stack-created VPC is gone. Exits non-zero if anything
remains.

`teardown.sh` reads the stack's `CreatedNetwork` / `VpcId` outputs **before**
deleting it. Networking is only ever touched when `CreatedNetwork=true` and only
for that exact VPC id — a VPC supplied through `VPC_ID`/`SUBNET_ID`
(`CreatedNetwork=false`) is left completely untouched.

## Emergency recovery

| Symptom | Action |
|---|---|
| backend unhealthy | `docker compose -f deploy/aws/compose/docker-compose.aws.yml restart backend` |
| frontend unhealthy | `... restart frontend` |
| Docker wedged | `sudo systemctl restart docker` then `... up -d` |
| a scan failed (bad repo / missing commit) | expected — the API returns a stable error code, the worker marks the scan `FAILED`, capacity is released; no action needed |
| Gemini unavailable | expected with no key — `POST /findings/{id}/explanation` returns `503 AI_EXPLANATION_UNAVAILABLE`; deterministic findings are unaffected |
| instance lost | re-run `deploy/aws/scripts/deploy.sh` (new public IP; SQLite starts empty) |

## What this is not

Single instance = single point of failure and a hard scaling ceiling. SQLite +
one in-process worker is deliberate for a demo with a handful of users. The
in-flight scan cap (`MAX_IN_FLIGHT_SCANS`, HTTP 429) and the body-size limit
are bounded back-pressure, not a production abuse-prevention system. See the
root `CRYPTIQ_FINAL_IMPLEMENTATION_READINESS_REPORT.md` §9 for the full list.
