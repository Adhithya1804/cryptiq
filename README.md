# Cryptiq Backend — Phases 9–12

Deterministic static-analysis engine for cryptographic inventory and PQC migration.

This repository contains the backend implementation for **Phases 9–12**:
- **Phase 9:** Bounded Static Impact Engine (`cryptiq.impact`)
- **Phase 10:** Migration Review Priority Engine (`cryptiq.priority`)
- **Phase 11:** Finding Fingerprints & Deterministic Scan Caching (`cryptiq.cache`)
- **Phase 12:** Database-backed Scan Worker (`cryptiq.worker` & `cryptiq.storage`)

## Architectural Constraints

- **Strictly deterministic:** Zero LLMs, zero probabilistic scoring, zero runtime instrumentation.
- **Zero heavy queue dependencies:** Database-backed job orchestration without Redis, Celery, Kafka, or external graph engines.
- **Auditable & evidence-backed:** Findings and blast-radius relationships are derived solely from static parse evidence. Reachability is never faked.

## Running Tests

All unit and integration tests run with zero external dependencies using Python's standard library:

```bash
# Using default python3
PYTHONPATH=src python3 -m unittest discover -s tests -v

# Or using python3.12
PYTHONPATH=src /opt/homebrew/bin/python3.12 -m unittest discover -s tests -v
```
