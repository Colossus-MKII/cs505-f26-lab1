#!/usr/bin/env python3
import os
import json
import time
import subprocess as sp
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ANSI escape sequences
RED = '\033[31m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
RESET = '\033[0m'

# available technology libraries
TECH_LIBS = {
    "asap7"   : {
        "lib" : "/common/users/shared/fluxlab-tools/techlibs/asap7sc7p5t_ALL_LVT_TT_nldm_211120.lib.gz",              
        "sim" : ["/common/users/shared/fluxlab-tools/techlibs/asap7sc7p5t_ALL_LVT_TT_nldm_211120.v"]
    },
    "nan45"       : {
        "lib" : "/common/users/shared/fluxlab-tools/techlibs/NangateOpenCellLibrary_typical.lib",
        "sim" : ["/common/users/shared/fluxlab-tools/techlibs/NangateOpenCellLibrary.v"]
    },
    "nan45-nand2"     : {
        "lib" : "/common/users/shared/fluxlab-tools/techlibs/NangateOpenCellLibrary_typical_NAND2.lib",
        "sim" : ["/common/users/shared/fluxlab-tools/techlibs/NangateOpenCellLibrary.v"]
    },
    "sky130"     : {
        "lib" : "/common/users/shared/fluxlab-tools/techlibs/sky130hd_tt.lib",
        "sim" : ["/common/users/shared/fluxlab-tools/techlibs/sky130hd_tt.v", "/common/users/shared/fluxlab-tools/techlibs/sky130hd_primitives.v"]
    }
}

# builds the cross product of a list of target modules and technology libraries
def build_all_targets(target_list: dict, techlib_list: list, build_dirname: str,
                      max_parallel_jobs: int, force: bool = False) -> int:
    print(f"Building {len(target_list)} modules using {len(techlib_list)} technology libraries")
    print(f"    Modules: {[i for i in target_list]}")
    print(f"    Techlibs: {techlib_list}")
    Path(build_dirname).mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    if max_parallel_jobs < 1:
        raise ValueError("max_parallel_jobs must be positive")

    def build_one(target_name, techlib_name):
        target_fullname = os.path.join(build_dirname, target_name, techlib_name)
        target_dir = Path(target_fullname)
        target_dir.mkdir(parents=True, exist_ok=True)
        config = {"target": target_list[target_name], "techlib": TECH_LIBS[techlib_name]}
        config_text = json.dumps(config, indent=2, sort_keys=True) + "\n"
        config_file = target_dir / ".config.json"
        # Configuration changes invalidate the existing synthesized netlist.
        if not config_file.exists() or config_file.read_text() != config_text:
            config_file.write_text(config_text)
        print(f"Building {target_name}/{techlib_name}", flush=True)
        env = os.environ.copy()
        env.update({
            "TECHLIB_LIB_FILENAME": TECH_LIBS[techlib_name]["lib"],
            "TECHLIB_SIM_FILENAMES": " ".join(TECH_LIBS[techlib_name]["sim"]),
            "MODULE_SOURCES": target_list[target_name]["sources"],
            "MODULE_TOP_NAME": target_list[target_name]["top"],
            "MODULE_SDC_FILENAME": target_list[target_name]["sdc"],
            "TESTBENCH_SOURCES": target_list[target_name]["tb sources"],
            "TESTBENCH_TOP_NAME": target_list[target_name]["tb top"],
            "CONFIG_FILENAME": str(config_file),
        })
        command = ["make", "--no-print-directory", "--no-builtin-rules",
                   f"BASE_OUTDIR={build_dirname}", f"TARGET_DIR={target_fullname}",
                   target_fullname]
        if force:
            command.append("--always-make")
        with (target_dir / "stdout.log").open("w") as out_file, \
                (target_dir / "stderr.log").open("w") as err_file:
            result = sp.run(command, env=env, stdout=out_file, stderr=err_file)
        return target_fullname, result.returncode

    failed = []
    with ThreadPoolExecutor(max_workers=max_parallel_jobs) as executor:
        futures = [executor.submit(build_one, target, tech)
                   for target in target_list for tech in techlib_list]
        for future in as_completed(futures):
            target_name, exit_code = future.result()
            color = GREEN if exit_code == 0 else RED
            print(color + f"[{time.time() - start_time:.2f} s] {target_name}: "
                  f"exit code {exit_code}" + RESET, flush=True)
            if exit_code:
                failed.append(target_name)
    if failed:
        print(RED + f"Failed targets: {', '.join(failed)}" + RESET)
    return 1 if failed else 0

# formats target modules in a standardized way
def format_target(sources : list, topname : str, sdc_filename: str, tb_sources: list, tb_top_name: str) -> dict:
    return {
        "sources" : " ".join(sources),
        "top" : topname,
        "sdc" : sdc_filename,
        "tb sources" : " ".join(tb_sources),
        "tb top" : tb_top_name
    }
