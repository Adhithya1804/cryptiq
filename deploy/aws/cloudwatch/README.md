# CloudWatch logging (demo-grade)

Two mechanisms, both standard, no framework:

| Source | Transport | Log group |
|---|---|---|
| `backend` container stdout | Docker `awslogs` driver | `/cryptiq/backend` |
| `frontend` container stdout (nginx-unprivileged access/error) | Docker `awslogs` driver | `/cryptiq/frontend` |
| `nginx` container stdout (public proxy access/error) | Docker `awslogs` driver | `/cryptiq/nginx` |
| `/var/log/cloud-init-output.log` (EC2 bootstrap) | CloudWatch agent | `/cryptiq/bootstrap` |

* Log groups are created by `cloudformation/cryptiq-demo.yaml` with
  `RetentionInDays: 3` (parameter `LogRetentionDays`, max 14). They are deleted
  with the stack, and `scripts/teardown.sh` deletes them again and verifies.
* The Docker daemon uses the **EC2 instance role** for the `awslogs` driver — no
  AWS keys on the host. The role can write only to the four `/cryptiq/*` groups
  (`iam/instance-role-policy.json`).
* The CloudWatch agent config is written inline by `user-data.sh`
  (`/opt/aws/amazon-cloudwatch-agent/etc/cryptiq.json`).

## Events emitted by the application

`app.logging_config.configure_logging()` sends the `app.*` loggers to stdout at
`LOG_LEVEL` (default `INFO`), so the Docker `awslogs` driver ships them:

| Event | Logger | Level |
|---|---|---|
| process startup (env, worker, docs flags) | `app.main` | INFO |
| readiness DB check failure | `app.api.v1.health` | ERROR |
| scan submitted / queued | `app.services.scans` | INFO |
| scan rejected (in-flight cap) | `app.services.scans` | WARNING |
| job claimed (attempt N) | `app.worker` | INFO |
| scan started (repo) | `app.worker` | INFO |
| scan completed (finding count, duration) | `app.worker` | INFO |
| scan failed (code, retry?) | `app.worker` | WARNING |
| worker iteration crash | `app.worker` | ERROR (exc) |
| Gemini explanation requested / completed | `app.services.explanations` | INFO |
| Gemini explanation unavailable / failed | `app.services.explanations` | WARNING |
| unhandled request error | `app.errors` | ERROR (exc) |

## Never logged

Secrets never reach a log line: `GEMINI_API_KEY`, `GITHUB_TOKEN`, AWS
credentials, `Authorization` / `Bearer` headers, and the repository archive
bytes. The ingestion and Gemini layers map external failures to fixed codes
before logging (`app/errors.py`, `app/integrations/`), and the explanation
service logs only the finding id and model name.

## Quick checks

```bash
aws logs tail /cryptiq/backend   --follow --region "$AWS_REGION"
aws logs tail /cryptiq/bootstrap --since 1h --region "$AWS_REGION"

# Prove no secret leaked:
for g in /cryptiq/backend /cryptiq/frontend /cryptiq/nginx /cryptiq/bootstrap; do
  aws logs filter-log-events --log-group-name "$g" --region "$AWS_REGION" \
    --filter-pattern '?GEMINI_API_KEY ?GITHUB_TOKEN ?Authorization ?Bearer' \
    --query 'events[].message' --output text
done   # expect: empty
```
