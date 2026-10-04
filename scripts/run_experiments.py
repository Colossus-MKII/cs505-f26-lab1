#!/usr/bin/env python3
"""Run verification, the 18 PPA experiments, analysis, and submission packaging."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_tools import TECH_LIBS


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', default='build')
    parser.add_argument('--results-dir', default='results')
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--skip-build', action='store_true',
                        help='Reanalyze existing builds; verification still runs.')
    parser.add_argument('--force', action='store_true', help='Rebuild all targets.')
    args = parser.parse_args()
    build_dir = (ROOT / args.build_dir).resolve()
    results_dir = (ROOT / args.results_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = build_dir / 'build-manifest.json'
    tools = {
        'yosys': ['/common/users/shared/fluxlab-tools/yosys-0.69/bin/yosys', '-V'],
        'opensta': ['/common/users/shared/fluxlab-tools/opensta-2.2.0/bin/sta', '-version'],
        'verilator': ['/common/users/shared/fluxlab-tools/verilator-5.052/bin/verilator', '--version'],
        'iverilog': ['iverilog', '-V'],
        'pdflatex': ['pdflatex', '--version'],
    }
    source_paths = sorted(list((ROOT / 'src').rglob('*')) +
                          list((ROOT / 'scripts').glob('*.py')) +
                          list((ROOT / 'scripts').glob('*.tcl')) +
                          [ROOT / 'scripts/verilator.vlt', ROOT / 'build.py', ROOT / 'Makefile'])
    source_hashes = {str(p.relative_to(ROOT)): digest(p) for p in source_paths if p.is_file()}
    libraries = {}
    for tech in ('asap7', 'nan45', 'sky130'):
        paths = [TECH_LIBS[tech]['lib'], *TECH_LIBS[tech]['sim']]
        libraries[tech] = {p: digest(Path(p)) for p in paths}
    versions = {}
    for name, command in tools.items():
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        versions[name] = {'command': command, 'returncode': result.returncode,
                          'output': (result.stdout + result.stderr).strip()}
    build_input_names = {
        'build.py', 'Makefile', 'scripts/build_tools.py', 'scripts/yosys.tcl',
        'scripts/opensta.tcl', 'scripts/verilator.vlt',
    }
    build_inputs = {name: value for name, value in source_hashes.items()
                    if name.startswith('src/') or name in build_input_names}
    provenance = {'source_sha256': build_inputs, 'library_sha256': libraries,
                  'tool_versions': {name: versions[name]['output']
                                    for name in ('yosys', 'opensta', 'verilator')}}
    if args.skip_build:
        if not manifest_path.is_file():
            parser.error('--skip-build requires a previous experiment manifest; run a full build first.')
        previous = json.loads(manifest_path.read_text())
        recorded = previous.get('build_provenance')
        if not recorded or any(recorded.get(key) != provenance[key]
                               for key in ('source_sha256', 'library_sha256', 'tool_versions')):
            parser.error('Existing build inputs differ or have no provenance; run without --skip-build.')
        provenance = recorded
    git_revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                  text=True, capture_output=True).stdout.strip()
    manifest = {'started_at_utc': stamp(), 'status': 'running',
                'python': sys.version, 'platform': platform.platform(),
                'base_git_revision': git_revision, 'tools': versions,
                'source_sha256': source_hashes, 'library_sha256': libraries,
                'build_provenance': provenance,
                'technologies': ['asap7', 'nan45', 'sky130'],
                'architectures': ['ripple-carry', 'kogge-stone', 'brent-kung'],
                'circuits': ['adder32', 'counter32'], 'commands': [],
                'skip_build': args.skip_build}

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

    def run(command):
        print('+ ' + ' '.join(map(str, command)), flush=True)
        manifest['commands'].append([str(x) for x in command])
        save()
        subprocess.run([str(x) for x in command], cwd=ROOT, check=True)

    save()
    try:
        run([sys.executable, 'scripts/verify_rtl.py', '--outdir', str(build_dir / 'formal')])
        if not args.skip_build:
            command = [sys.executable, 'build.py', str(build_dir), '--jobs', str(args.jobs)]
            if args.force:
                command.append('--force')
            run(command)
            manifest['build_provenance']['completed_at_utc'] = stamp()
            save()
        run([sys.executable, 'scripts/analyze_results.py', '--build-dir', str(build_dir),
             '--output-dir', str(results_dir)])
        manifest['status'] = 'analysis_complete'
        save()
        run([sys.executable, 'scripts/make_report.py', '--results-dir', str(results_dir),
             '--manifest', str(manifest_path)])
        submission = ROOT / 'submission.zip'
        with zipfile.ZipFile(submission, 'w', zipfile.ZIP_DEFLATED) as archive:
            for rel in ('src/adder32/adder32-kogge-stone.v',
                        'src/adder32/adder32-brent-kung.v', 'report.pdf',
                        'src/adder32/adder32-testbench.v',
                        'src/counter32/counter32-testbench.v'):
                archive.write(ROOT / rel, arcname=Path(rel).name)
        testbenches = ROOT / 'testbenches.zip'
        with zipfile.ZipFile(testbenches, 'w', zipfile.ZIP_DEFLATED) as archive:
            for circuit in ('adder32', 'counter32'):
                source = ROOT / 'src' / circuit / f'{circuit}-testbench.v'
                archive.write(source, arcname=source.name)
        current_build_inputs = {name: digest(ROOT / name) for name in build_inputs}
        if current_build_inputs != build_inputs:
            raise ValueError('Build inputs changed during the experiment; rerun the full workflow.')
        manifest['source_sha256_at_start'] = source_hashes
        manifest['source_sha256'] = {str(p.relative_to(ROOT)): digest(p)
                                     for p in source_paths if p.is_file()}
        manifest['artifact_sha256'] = {
            str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): digest(p)
            for p in (results_dir / 'results.json', results_dir / 'results.csv', ROOT / 'report.pdf')
        }
        manifest['status'] = 'complete'
        manifest['completed_at_utc'] = stamp()
        manifest['submission_sha256'] = digest(submission)
        manifest['testbenches_sha256'] = digest(testbenches)
        save()
        print(f'Complete: {ROOT / "report.pdf"}, {submission}', flush=True)
    except (subprocess.CalledProcessError, OSError, ValueError) as error:
        manifest['status'] = 'failed'
        manifest['failure'] = str(error)
        save()
        raise


if __name__ == '__main__':
    main()
