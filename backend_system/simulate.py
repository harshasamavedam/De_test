"""CLI entrypoint for the shop synthetic-data simulator.

Examples
--------
    # 30 days, 500-2000 visitors/day, 3.5% conversion, reproducible
    python simulate.py --days 30 --users-per-day 500-2000 --conversion 3.5 --seed 42

    # fresh start (drops the shop keyspace) against local Cassandra
    python simulate.py --days 90 --users-per-day 1000-5000 --conversion 4 --reset

    # validate generation logic without Cassandra
    python simulate.py --days 7 --users-per-day 200-400 --conversion 5 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal

from shop import config
from shop.simulator import SimParams, Simulator
from shop.writer import DEFAULT_MAX_INFLIGHT, Writer


def parse_users_per_day(value: str) -> tuple[int, int]:
    if "-" in value:
        low_s, high_s = value.split("-", 1)
        low, high = int(low_s), int(high_s)
    else:
        low = high = int(value)
    if low < 1 or high < 1 or low > high:
        raise argparse.ArgumentTypeError(
            f"invalid range '{value}': expected MIN-MAX with MIN>=1 and MIN<=MAX"
        )
    return low, high


def parse_start_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date '{value}', use YYYY-MM-DD") from exc


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=config.DEFAULT_DAYS,
                        help="number of days to simulate (default: %(default)s)")
    parser.add_argument("--users-per-day", type=parse_users_per_day,
                        default=config.DEFAULT_USERS_PER_DAY,
                        help="daily visitor range MIN-MAX (default: 500-2000)")
    parser.add_argument("--conversion", type=Decimal, default=config.DEFAULT_CONVERSION,
                        help="target sessions -> orders percent (default: %(default)s)")
    parser.add_argument("--start-date", type=parse_start_date, default=date.today(),
                        help="first simulated day YYYY-MM-DD (default: today)")
    parser.add_argument("--seed", type=int, default=config.DEFAULT_SEED,
                        help="RNG seed for reproducibility (default: %(default)s)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9042)
    parser.add_argument("--keyspace", default=config.DEFAULT_KEYSPACE)
    parser.add_argument("--dirty", default=config.DEFAULT_DIRTY_PROFILE,
                        choices=("clean", "realistic"))
    parser.add_argument("--reset", action="store_true",
                        help="drop and recreate the keyspace first")
    parser.add_argument("--dry-run", action="store_true",
                        help="generate in memory and print a summary, no DB writes")
    parser.add_argument("--max-inflight", type=int, default=DEFAULT_MAX_INFLIGHT,
                        help="max concurrent in-flight writes (default: %(default)s)")
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days must be >= 1")
    if not (Decimal("0") <= args.conversion <= Decimal("100")):
        parser.error("--conversion must be between 0 and 100")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    params = SimParams(
        days=args.days,
        users_per_day=args.users_per_day,
        conversion=args.conversion,
        start_date=args.start_date,
        seed=args.seed,
        keyspace=args.keyspace,
        dirty=args.dirty,
    )
    writer = Writer(args.host, args.port, args.keyspace, dry_run=args.dry_run,
                    max_inflight=args.max_inflight)
    simulator = Simulator(params, writer)
    summary = simulator.run(reset=args.reset)

    print(json.dumps(summary, indent=2, default=str))
    if not args.dry_run:
        print("\nWrote data to Cassandra keyspace "
              f"'{args.keyspace}' at {args.host}:{args.port}.")
    else:
        print("\nDry run complete; no data was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
