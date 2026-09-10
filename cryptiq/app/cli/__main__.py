"""``python -m app.cli`` shim."""

from app.cli.main import main

raise SystemExit(main())
