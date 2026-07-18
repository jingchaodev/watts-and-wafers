#!/usr/bin/env python3
"""CLI entry point: run one or more collectors in isolation.

Usage:
    python3 run.py --group hourly     # vast, neoclouds, composite
    python3 run.py --group daily      # hyperscaler, openrouter, memory, composite
    python3 run.py --only vast        # run a single named collector

Every collector's main() is invoked in its own try/except so one crashing
collector (an uncaught exception escaping its own error handling) never
prevents the others from running. Exit code is 0 unless EVERY collector run
in this invocation failed (raised or returned nonzero).
"""
import argparse
import sys

import composite
import crosscheck
import hyperscaler
import memory
import neoclouds
import openrouter
import vast

COLLECTORS = {
    "vast": vast,
    "neoclouds": neoclouds,
    "hyperscaler": hyperscaler,
    "openrouter": openrouter,
    "memory": memory,
    "composite": composite,
    "crosscheck": crosscheck,
}

GROUPS = {
    "hourly": ["vast", "neoclouds", "composite"],
    "daily": ["hyperscaler", "openrouter", "memory", "composite", "crosscheck"],
}


def run_one(name):
    """Run one collector's main(), isolating any exception. Returns True on
    success (main() returned 0), False otherwise."""
    mod = COLLECTORS[name]
    try:
        rc = mod.main()
        ok = (rc == 0)
        if not ok:
            print(f"[run] {name} exited nonzero ({rc})", file=sys.stderr)
        return ok
    except Exception as e:  # noqa: BLE001 - never let one collector kill the run
        print(f"[run] {name} CRASHED: {e!r}", file=sys.stderr)
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Watts & Wafers collector runner")
    group_arg = parser.add_mutually_exclusive_group(required=True)
    group_arg.add_argument("--group", choices=sorted(GROUPS.keys()), help="Named group to run")
    group_arg.add_argument("--only", choices=sorted(COLLECTORS.keys()), help="Run a single collector")
    args = parser.parse_args(argv)

    if args.only:
        names = [args.only]
    else:
        names = list(GROUPS[args.group])

    results = {}
    for name in names:
        print(f"[run] --- {name} ---")
        results[name] = run_one(name)

    n_ok = sum(1 for v in results.values() if v)
    n_total = len(results)
    print(f"[run] done: {n_ok}/{n_total} collectors ok ({results})")

    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
