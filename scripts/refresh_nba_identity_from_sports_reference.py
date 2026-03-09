from __future__ import annotations

import argparse
import json

from app.identity_resolution import _player_directory
from app.sports_reference_identity import refresh_nba_identity_from_basketball_reference


def main() -> None:
    parser = argparse.ArgumentParser(description='Refresh NBA identity caches from Basketball-Reference')
    parser.add_argument('--gzip', action='store_true', help='Also emit .gz cache files')
    args = parser.parse_args()

    result = refresh_nba_identity_from_basketball_reference(gzip_output=args.gzip)
    _player_directory.cache_clear()
    print(json.dumps({'ok': True, **result}))


if __name__ == '__main__':
    main()
