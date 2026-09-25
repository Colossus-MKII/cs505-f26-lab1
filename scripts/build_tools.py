#!/usr/bin/env python3
import sys
import os
import time
import subprocess as sp
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

# waits until less than a maximum number of processes is running
def wait_until_nprocs_leq_target(procs, target, start_time, n_pending):
    while len(procs) > target:
        seconds_elapsed = time.time() - start_time
        print(f"[{seconds_elapsed:#.2f} s] {len(procs)} jobs running; {n_pending} jobs pending")
        for jobname, p in procs:
            exit_code = p.poll()
            if exit_code != None:
                print((GREEN if exit_code == 0 else RED) + f"Job \"{jobname}\" (PID {p.pid}) finished with exit code {exit_code}" + RESET)
                procs.remove((jobname, p))
        time.sleep(1) 

# builds the cross product of a list of target modules and technology libraries
def build_all_targets(target_list: list, techlib_list: dict, build_dirname: str, max_parallel_jobs: int) -> None:
    print(f"Building {len(target_list)} modules using {len(techlib_list)} technology libraries")
    print(f"    Modules: {[i for i in target_list]}")
    print(f"    Techlibs: {techlib_list}")
    Path(build_dirname).mkdir(parents=False, exist_ok=True)

    start_time = time.time()

    TOTAL_JOBS = len(target_list) * len(techlib_list)
    n_pending = TOTAL_JOBS

    assert max_parallel_jobs > 0
    procs = []
    log_file_handles = []
    try:
        for target_name in target_list:
            for techlib_name in techlib_list:
                if len(procs) >= max_parallel_jobs:
                    wait_until_nprocs_leq_target(procs, max_parallel_jobs - 1, start_time, n_pending)
                
                target_fullname = os.path.join(build_dirname, target_name, techlib_name)
                Path(target_fullname).mkdir(parents=True, exist_ok=True)
                print(f"Building target name \"{target_name}\" using technology library \"{techlib_name}\" (output dir: \"{target_fullname}\")")
                
                out_file = open(f"{target_fullname}/stdout.log", "w", encoding="utf-8")
                err_file = open(f"{target_fullname}/stderr.log", "w", encoding="utf-8")
                log_file_handles.extend([out_file, err_file])

                env = os.environ.copy()
                env["TECHLIB_LIB_FILENAME"] = TECH_LIBS[techlib_name]["lib"]
                env["TECHLIB_SIM_FILENAMES"] = " ".join(TECH_LIBS[techlib_name]["sim"])
                env["MODULE_SOURCES"] = target_list[target_name]["sources"]
                env["MODULE_TOP_NAME"] = target_list[target_name]["top"]
                env["MODULE_SDC_FILENAME"] = target_list[target_name]["sdc"]
                env["TESTBENCH_SOURCES"] = target_list[target_name]["tb sources"]
                env["TESTBENCH_TOP_NAME"] = target_list[target_name]["tb top"]
                # print(env)

                proc = sp.Popen(args=["make", target_fullname, "-rd"], env=env, stdout=out_file, stderr=err_file)

                procs.append((target_fullname, proc))
                n_pending -= 1

        wait_until_nprocs_leq_target(procs, 0, start_time, n_pending)
    finally:
        for f in log_file_handles:
            f.close()

# formats target modules in a standardized way
def format_target(sources : list, topname : str, sdc_filename: str, tb_sources: list, tb_top_name: str) -> dict:
    return {
        "sources" : " ".join(sources),
        "top" : topname,
        "sdc" : sdc_filename,
        "tb sources" : " ".join(tb_sources),
        "tb top" : tb_top_name
    }