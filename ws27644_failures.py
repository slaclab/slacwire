"""Check WS27644 failure count between 6/17 and 6/19 (bug discovery window)."""

import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from slacwire.registry.registry_sqlite import convert_run_registry_json_to_sqlite

SOURCE_JSON = Path("/u1/lcls/physics/data/wire_scan/ws_run_registry.json")


def main():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        convert_run_registry_json_to_sqlite(SOURCE_JSON, tmp.name, overwrite=True)
        engine = create_engine(f"sqlite:///{tmp.name}")

        with engine.connect() as conn:
            results = conn.execute(
                text("""
                    SELECT DATE(timestamp_iso) AS day, COUNT(*) AS failure_count
                    FROM runs
                    WHERE wire = :wire
                      AND status = 'error'
                      AND timestamp_iso >= :start
                      AND timestamp_iso < :end
                    GROUP BY day
                    ORDER BY day
                """),
                {"wire": "WS27644", "start": "2026-06-17T00:00:00", "end": "2026-06-20T00:00:00"},
            )
            for row in results:
                print(row.day, row.failure_count)


if __name__ == "__main__":
    main()
