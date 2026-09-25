#!/usr/bin/env python3
import sys
import os
import time
import subprocess as sp
from pathlib import Path

import scripts.build_tools as build_tools

# lab1: insert your own extra adders here
ADDER_SOURCES = {
    "ripple-carry" : ["src/adder32/adder32-ripple-carry.v"],
    # TODO: "kogge-stone" : ["src/adder32/adder32-kogge-stone.v"],
    # TODO: ... your own extra adders you decide to build
}

def configure_adder_build(adder_names : list) -> None:
    target_list = {}
    
    # all the different adder32's and counter 32's
    for adder_name in adder_names:
        target_list["adder32-" + adder_name] = build_tools.format_target(
            ADDER_SOURCES[adder_name],
            "adder32",
            "src/adder32/adder32.sdc",
            ["src/adder32/adder32-testbench.v"],
            "adder32_testbench"
        )

        target_list["counter32-" + adder_name] = build_tools.format_target(
            ADDER_SOURCES[adder_name] + ["src/counter32/counter32.v"],
            "counter32",
            "src/counter32/counter32.sdc",
            ["src/counter32/counter32-testbench.v"],
            "counter32_testbench"
        )

    return target_list

if __name__ == "__main__":

    if len(sys.argv) != 2:
        print(f"[ERROR] usage: {sys.argv[0]} <str: name of build output directory>")
        sys.exit(-1)

    # builds all adders in all technology libraries
    adder_targets = configure_adder_build(ADDER_SOURCES.keys())
    build_tools.build_all_targets(target_list=adder_targets, techlib_list=build_tools.TECH_LIBS.keys(), build_dirname=sys.argv[1], max_parallel_jobs=3)
    
    # lab1: example of building only {ripple-carry} x {asap7}
    # adder_targets = configure_adder_build(["ripple-carry"])
    # build_tools.build_all_targets(target_list=adder_targets, techlib_list=["asap7", "nan45", "sky130"], build_dirname=sys.argv[1], max_parallel_jobs=3)
    