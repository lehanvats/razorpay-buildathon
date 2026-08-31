"""Run one SQL statement against whatever DATABASE_URL points at.

The e2e script used to shell out to `docker exec ... psql`, which silently
assumed a local container. Going through app.config here means the check
follows the app to Neon (or anywhere else) instead of asserting against a
database the app is no longer using — the failure mode being a suite that
passes green while testing the wrong server.

Prints a single scalar, or an empty line for NULL / no rows.
"""

import sys
from pathlib import Path

# Running `python scripts/dbq.py` puts scripts/ on sys.path, not the backend
# root, so `app` would not import. The app is not pip-installed in this venv.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import settings  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: dbq.py '<sql>'", file=sys.stderr)
        return 2

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        result = conn.execute(text(sys.argv[1]))
        if result.returns_rows:
            row = result.first()
            value = None if row is None else row[0]
            # Match psql -tA: booleans render as t/f, NULL as empty.
            if value is None:
                print("")
            elif isinstance(value, bool):
                print("t" if value else "f")
            else:
                print(value)
        conn.commit()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
