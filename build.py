#!/usr/bin/env python3
"""Build selected adders and counters with the laboratory synthesis flow."""
import argparse

import scripts.build_tools as build_tools


ADDER_SOURCES = {
    "ripple-carry": ["src/adder32/adder32-ripple-carry.v"],
    "kogge-stone": ["src/adder32/adder32-kogge-stone.v"],
    "brent-kung": ["src/adder32/adder32-brent-kung.v"],
}
DEFAULT_TECHLIBS = ["asap7", "nan45", "sky130"]


def configure_adder_build(adder_names: list) -> dict:
    targets = {}
    for name in adder_names:
        targets["adder32-" + name] = build_tools.format_target(
            ADDER_SOURCES[name], "adder32", "src/adder32/adder32.sdc",
            ["src/adder32/adder32-testbench.v"], "adder32_testbench",
        )
        targets["counter32-" + name] = build_tools.format_target(
            ADDER_SOURCES[name] + ["src/counter32/counter32.v"],
            "counter32", "src/counter32/counter32.sdc",
            ["src/counter32/counter32-testbench.v"], "counter32_testbench",
        )
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", help="output directory, normally build")
    parser.add_argument("--adders", nargs="+", choices=ADDER_SOURCES,
                        default=list(ADDER_SOURCES))
    parser.add_argument("--techlibs", nargs="+", choices=build_tools.TECH_LIBS,
                        default=DEFAULT_TECHLIBS)
    parser.add_argument("--jobs", type=int, default=3,
                        help="maximum simultaneous target builds (default: 3)")
    parser.add_argument("--force", action="store_true",
                        help="rebuild all selected targets regardless of timestamps")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if any(c.isspace() for c in args.build_dir):
        parser.error("the build directory must not contain whitespace")
    return build_tools.build_all_targets(
        configure_adder_build(list(dict.fromkeys(args.adders))),
        list(dict.fromkeys(args.techlibs)), args.build_dir, args.jobs,
        force=args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
