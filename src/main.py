from __future__ import annotations

import logging
import sys

from .bot import run
from .config import load_config, validate_config


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config()
    errors = validate_config(config)
    if errors:
        print("Configuration error:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1

    run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
