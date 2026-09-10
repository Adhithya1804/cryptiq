#!/bin/bash
# Cryptiq EC2 bootstrap — runs once on first boot, invoked by the CloudFormation
# stack's UserData after the repository is cloned to /opt/cryptiq/app.
#
# Steps:
#   1. install Docker + the Compose plugin + the CloudWatch agent
#   2. mount the dedicated encrypted EBS volume at /data (SQLite lives here)
#   3. pull optional secrets from SSM Parameter Store into /opt/cryptiq/.env
#   4. bring up the demo stack (deploy/aws/compose/docker-compose.aws.yml)
#   5. wait for frontend + backend health, then backend readiness
#
# It is idempotent enough to re-run from an SSM session if a step fails.
set -euxo pipefail

REGION="${AWS_REGION:-us-east-1}"
APP_DIR="${APP_DIR:-/opt/cryptiq/app}"
ENV_FILE="/opt/cryptiq/.env"
DATA_MNT="/data"
COMPOSE_FILE="deploy/aws/compose/docker-compose.aws.yml"
COMPOSE_VERSION="v2.29.7"

echo "cryptiq-bootstrap: starting at $(date -u +%FT%TZ) region=${REGION} ref=$(git -C "${APP_DIR}" rev-parse --short HEAD 2>/dev/null || echo '?')"

# --- 1. Docker + Compose plugin + CloudWatch agent ----------------------- #
dnf install -y docker amazon-cloudwatch-agent
systemctl enable --now docker
usermod -aG docker ec2-user || true

mkdir -p /usr/local/lib/docker/cli-plugins
if ! docker compose version >/dev/null 2>&1; then
  arch="$(uname -m)"; case "${arch}" in x86_64) arch=x86_64;; aarch64) arch=aarch64;; esac
  curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose \
    "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-${arch}"
  chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi
docker compose version

# --- 2. Mount the SQLite data volume ----------------------------------- #
# The CFN stack attaches a second EBS volume at /dev/sdf; on Nitro it appears
# as an NVMe device. Pick the one block device with no filesystem and no
# mountpoint.
data_dev=""
for dev in $(lsblk -dpno NAME,TYPE | awk '$2=="disk"{print $1}'); do
  root_dev="$(findmnt -no SOURCE / | sed 's/p\?[0-9]*$//')"
  [ "${dev}" = "${root_dev}" ] && continue
  if [ -z "$(lsblk -no MOUNTPOINT "${dev}")" ]; then data_dev="${dev}"; break; fi
done

mkdir -p "${DATA_MNT}"
if [ -n "${data_dev}" ]; then
  if ! blkid "${data_dev}"; then
    mkfs.xfs -q "${data_dev}"
  fi
  uuid="$(blkid -s UUID -o value "${data_dev}")"
  grep -q "${uuid}" /etc/fstab || echo "UUID=${uuid} ${DATA_MNT} xfs defaults,nofail 0 2" >> /etc/fstab
  mount -a
else
  echo "cryptiq-bootstrap: WARNING no dedicated data volume found; SQLite will live on the root volume"
fi
# The backend container runs as uid 1001 and must own its data dir.
mkdir -p "${DATA_MNT}"
chown -R 1001:1001 "${DATA_MNT}"

# --- 3. Secrets from SSM Parameter Store ------------------------------- #
mkdir -p /opt/cryptiq
umask 077
: > "${ENV_FILE}"
gemini_key="$(aws ssm get-parameter --region "${REGION}" --name /cryptiq/GEMINI_API_KEY \
  --with-decryption --query Parameter.Value --output text 2>/dev/null || true)"
if [ -n "${gemini_key}" ] && [ "${gemini_key}" != "None" ]; then
  printf 'GEMINI_API_KEY=%s\n' "${gemini_key}" >> "${ENV_FILE}"
  echo "cryptiq-bootstrap: GEMINI_API_KEY loaded from SSM (value not logged)"
else
  echo "cryptiq-bootstrap: no /cryptiq/GEMINI_API_KEY in SSM — AI explanation path will return 503 (expected)"
fi
unset gemini_key
chmod 600 "${ENV_FILE}"
chown root:root "${ENV_FILE}"

# --- 4. CloudWatch agent for the bootstrap log ------------------------ #
cat > /opt/aws/amazon-cloudwatch-agent/etc/cryptiq.json <<JSON
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/cloud-init-output.log",
            "log_group_name": "${CRYPTIQ_BOOTSTRAP_LOG_GROUP:-/cryptiq/bootstrap}",
            "log_stream_name": "{instance_id}/cloud-init",
            "retention_in_days": 3
          }
        ]
      }
    }
  }
}
JSON
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/cryptiq.json

# --- 5. Bring up the stack ------------------------------------------- #
cd "${APP_DIR}"
export AWS_REGION="${REGION}"
docker compose -f "${COMPOSE_FILE}" up -d --build

# --- 6. Health gate ------------------------------------------------- #
ok() { curl -fsS -o /dev/null --max-time 5 "$1"; }
for probe in \
  "http://localhost/healthz|nginx" \
  "http://localhost/api/v1/health|backend liveness" \
  "http://localhost/api/v1/health/ready|backend readiness" ; do
  url="${probe%%|*}"; name="${probe##*|}"
  for attempt in $(seq 1 60); do
    if ok "${url}"; then echo "cryptiq-bootstrap: ${name} OK (${url})"; break; fi
    if [ "${attempt}" -eq 60 ]; then
      echo "cryptiq-bootstrap: FAILED ${name} never became healthy (${url})"
      docker compose -f "${COMPOSE_FILE}" ps
      exit 1
    fi
    sleep 5
  done
done

echo "cryptiq-bootstrap: complete at $(date -u +%FT%TZ) — http://$(curl -fsS --max-time 3 http://169.254.169.254/latest/meta-data/public-ipv4 || echo '<public-ip>')/"
