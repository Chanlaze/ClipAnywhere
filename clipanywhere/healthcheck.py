from __future__ import annotations

import argparse
import sys
from urllib.request import Request, urlopen

from .common import load_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/config/server_config.json")
    args = parser.parse_args()

    config = load_json(args.config)
    url = f"http://127.0.0.1:{int(config['port'])}/health"
    req = Request(url, headers={"Authorization": f"Bearer {config['token']}"})
    try:
        with urlopen(req, timeout=3) as response:
            sys.exit(0 if response.status == 200 else 1)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()

