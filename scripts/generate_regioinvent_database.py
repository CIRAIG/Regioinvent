#!/usr/bin/env python3
"""
Generate a regionalized Brightway database with regioinvent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import regioinvent


SUPPORTED_ECOINVENT_VERSIONS = ("3.9", "3.9.1", "3.10", "3.10.1")
SUPPORTED_LCIA_METHODS = ("IW v2.1", "EF v3.1", "ReCiPe 2016 v1.03 (H)", "all")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--bw-project-name", required=True, help="Brightway project name")
    parser.add_argument(
        "--ecoinvent-database-name",
        required=True,
        help="Existing ecoinvent database name inside the Brightway project",
    )
    parser.add_argument(
        "--ecoinvent-version",
        required=True,
        choices=SUPPORTED_ECOINVENT_VERSIONS,
        help="Supported ecoinvent version string",
    )
    parser.add_argument(
        "--trade-database-path",
        required=True,
        help="Path to the external SQLite trade database",
    )
    parser.add_argument(
        "--cutoff",
        type=float,
        default=0.99,
        help="Cutoff used to aggregate remaining shares into RoW",
    )
    parser.add_argument(
        "--target-db-name",
        default=None,
        help="Optional output Brightway database name",
    )
    parser.add_argument(
        "--lcia-method",
        choices=SUPPORTED_LCIA_METHODS,
        default=None,
        help="Optional packaged regionalized LCIA method import",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trade_db_path = Path(args.trade_database_path).expanduser().resolve()
    if not trade_db_path.exists():
        raise SystemExit(f"Trade database not found: {trade_db_path}")

    regio = regioinvent.Regioinvent(
        bw_project_name=args.bw_project_name,
        ecoinvent_database_name=args.ecoinvent_database_name,
        ecoinvent_version=args.ecoinvent_version,
    )

    try:
        regio.spatialize_my_ecoinvent()
        if args.lcia_method:
            regio.import_fully_regionalized_impact_method(args.lcia_method)
        regio.regionalize_ecoinvent_with_trade(
            trade_database_path=str(trade_db_path),
            target_database_name=args.target_db_name or f"{args.ecoinvent_database_name} - regioinvent",
            cutoff=args.cutoff,
        )
    finally:
        if getattr(regio, "trade_conn", None):
            regio.trade_conn.close()

    print(
        "Wrote Brightway databases: "
        f"{regio.regionalized_ecoinvent_db_name} and {regio.target_db_name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
