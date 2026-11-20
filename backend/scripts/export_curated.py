"""Write the curated quests to the frontend's guide snapshot.

Usage
-----
    python -m scripts.export_curated

`frontend/scripts/curated-snapshot.json` is the checked-in data the static
guide pages (`/guides/…`) and the marketing-card page are built from, so a
frontend build never depends on the API being up. Run this after any change
under `curated/` and commit the result.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from curated_quests import CURATED_CITIES  # noqa: E402

_SNAPSHOT = _BACKEND_DIR.parent / "frontend" / "scripts" / "curated-snapshot.json"


def main() -> None:
    snapshot = {
        "cities": [
            {
                "key": city.key,
                "name": city.name,
                # Same JSON the API serves, so the guides and the app agree.
                "quests": [quest.model_dump(mode="json") for quest in city.quests],
            }
            for city in CURATED_CITIES
        ]
    }
    _SNAPSHOT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(c["quests"]) for c in snapshot["cities"])
    print(f"Wrote {total} quests across {len(snapshot['cities'])} cities -> {_SNAPSHOT}")


if __name__ == "__main__":
    main()
