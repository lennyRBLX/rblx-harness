"""Discover human-saved captures and accept only a matching, covered event window."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

LIMIT = 128 * 1024 * 1024


def digest(path):
    if path.stat().st_size > LIMIT:
        raise ValueError('capture size limit')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(roots):
    files = {}
    for root in roots:
        for pattern in ('microprofile*.html', '*viewer-data.json'):
            for path in Path(root).expanduser().glob(pattern):
                if path.is_file() and not path.is_symlink():
                    stat = path.stat()
                    files[str(path.resolve())] = [stat.st_mtime_ns, stat.st_size, digest(path)]
    return files


def export_html(path, destination, node='node', timeout=60):
    destination.mkdir(parents=True, exist_ok=True)
    output = subprocess.run([node, '--max-old-space-size=512', str(Path(__file__).with_name('export_html.cjs')),
                             str(path), str(destination)], capture_output=True, text=True, timeout=timeout)
    if output.returncode:
        raise ValueError('HTML export rejected: ' + output.stderr.splitlines()[0][:180])
    return destination / 'viewer-data.json'


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('nonfinite event data')
    return value


def analyze(data, place, markers, mode, minimum, expected=None, spike_ms=20, run=None):
    """Use event arrays only. Native rolling aggregates are never mixed in."""
    if str(data.get('GeneralInfo', {}).get('PlaceId')) != str(place):
        raise ValueError('wrong place')
    if minimum < 1 or not math.isfinite(spike_ms) or spike_ms <= 0 or mode not in {'sample', 'full'}:
        raise ValueError('invalid window bounds')
    if len(set(markers)) != len(markers) or not markers:
        raise ValueError('unique workload markers required')
    if mode == 'full' and (not isinstance(expected, int) or not 1 <= expected <= 100000):
        raise ValueError('expected frame count must be 1..100000')
    marker_runs = {m.split('/')[1] for m in markers if m.startswith('Harness/') and len(m.split('/')) > 2}
    if len(marker_runs) > 1:
        raise ValueError('different run windows')
    run = run or next(iter(marker_runs), None)
    available_run = data.get('RunId', data.get('GeneralInfo', {}).get('RunId'))
    if run and available_run is not None and str(available_run) != run:
        raise ValueError('wrong run identity')
    if run and any(m.startswith('Harness/') and not m.startswith('Harness/' + run + '/') for m in markers):
        raise ValueError('marker run mismatch')
    frames, timers = data.get('Frames'), data.get('TimerInfo')
    if not isinstance(frames, list) or not frames or not isinstance(timers, list):
        raise ValueError('unsupported viewer data')
    if any(data.get('ThreadClobbered', [])):
        raise ValueError('clobbered capture')
    names = {t['id']: t['name'] for t in timers}
    selected = {marker: {} for marker in markers}
    indices = {marker: [] for marker in markers}
    for index, frame in enumerate(frames):
        for thread, types in enumerate(frame.get('tt', [])):
            try:
                ids, times = frame['ti'][thread], frame['ts'][thread]
                if len(types) != len(ids) or len(types) != len(times):
                    raise ValueError('incomplete event arrays')
                stack = []
                for kind, timer, instant in zip(types, ids, times):
                    if kind not in (0, 1):
                        continue  # Label/counter payloads are not event timestamps.
                    instant = finite(instant)
                    name = names.get(timer, '')
                    matching = [m for m in markers if name == m or name.startswith(m + '/')]
                    if kind == 1:
                        stack.append((timer, instant, matching, name))
                    elif kind == 0:
                        if not stack:
                            if matching: raise ValueError('partial workload scope')
                            continue
                        start_id, begin, matches, start_name = stack.pop()
                        if start_id != timer:
                            if matching or matches: raise ValueError('mismatched workload scope')
                            continue
                        for marker in matches:
                            if frame.get('paused') or frame.get('incomplete') or instant < begin:
                                raise ValueError('incomplete workload frame')
                            selected[marker].setdefault(index, []).append(instant - begin)
                            suffix = start_name[len(marker):].strip('/')
                            if suffix.isdigit(): indices[marker].append(int(suffix))
                if any(item[2] for item in stack):
                    raise ValueError('partial workload scope')
            except (KeyError, IndexError, TypeError) as e:
                raise ValueError('incomplete event arrays') from e
    reports = []
    for marker, observations in selected.items():
        active = sorted(observations)
        if not active:
            raise ValueError('workload marker absent: ' + marker)
        if len(active) < minimum or active != list(range(active[0], active[-1] + 1)):
            raise ValueError('insufficient or discontinuous coverage')
        if mode == 'full' and (expected is None or sorted(indices[marker]) != list(range(1, expected + 1))):
            raise ValueError('partial capture; full measurement coverage required')
        if indices[marker] and (len(set(indices[marker])) != len(indices[marker]) or sorted(indices[marker]) != list(range(min(indices[marker]), max(indices[marker])+1))):
            raise ValueError('duplicate or missing workload indices')
        periods = []
        for index in active:
            frame = frames[index]
            duration = finite(frame['frameend']) - finite(frame['framestart'])
            if duration <= 0: raise ValueError('invalid frame interval')
            periods.append(duration)
        costs = [sum(observations[index]) for index in active]
        spikes = [(i, d) for i, d in zip(active, periods) if d > spike_ms]
        reports.append(dict(marker=marker, coverage=mode, first=active[0], last=active[-1], frames=len(active),
                            scope_average_ms=sum(costs)/len(costs), scope_max_ms=max(costs),
                            frame_average_ms=sum(periods)/len(periods), frame_max_ms=max(periods),
                            spike_threshold_ms=spike_ms, spikes=spikes[:256], overflow=max(0,len(spikes)-256)))
    return reports


def render(reports):
    return '\n'.join(f"PROFILE|{r['marker']}|{r['coverage']} frames={r['frames']}|scope-average={r['scope_average_ms']:.3f}ms|frame-interval-average={r['frame_average_ms']:.3f}ms|spikes={len(r['spikes'])+r['overflow']} max={r['frame_max_ms']:.3f}ms overflow={r['overflow']}" for r in reports)


def collect(baseline, roots, output, place, markers, mode='sample', minimum=1, expected=None,
            spike_ms=20, wait=5, node='node', selected_path=None, run=None):
    deadline = time.monotonic() + wait
    observations = {}
    failures = {}
    while True:
        now = inventory(roots)
        # Newest order ranks candidates; identity/coverage decide acceptance.
        candidates = sorted((p for p in now if now[p] != baseline.get(p)), key=lambda p: now[p][0], reverse=True)
        if len(candidates) > 64:
            raise ValueError("candidate limit; narrow dump directories")
        accepted = []
        pending = []
        with tempfile.TemporaryDirectory(prefix='harness-capture-') as temp:
            for index, filename in enumerate(candidates):
                if selected_path and Path(filename).resolve() != Path(selected_path).resolve(): continue
                stamp = now[filename]
                previous = observations.get(filename)
                if previous is None or previous[0] != stamp:
                    observations[filename] = (stamp, time.monotonic())
                    pending.append(filename)
                    continue
                if time.monotonic() - previous[1] < 0.5:
                    pending.append(filename)
                    continue
                path = Path(filename)
                directory = Path(temp) / str(index)
                try:
                    parsed = export_html(path, directory, node, max(0.01, min(60, deadline-time.monotonic()))) if path.suffix == '.html' else path
                    data = json.loads(parsed.read_text())
                    reports = analyze(data, place, markers, mode, minimum, expected, spike_ms, run)
                    if digest(path) != stamp[2]:
                        pending.append(filename); continue
                    accepted.append((path, directory, stamp[2], reports))
                except (json.JSONDecodeError, OSError, subprocess.TimeoutExpired) as error:
                    failures[filename] = str(error)
                    pending.append(filename)
                except ValueError as error:
                    failures[filename] = str(error)
                    if 'unexpected end' in str(error).lower() or 'capture magic' in str(error).lower():
                        pending.append(filename)
            # A still-writing candidate can become a second match. Never accept around it.
            if len(accepted) > 1:
                raise ValueError('ambiguous captures: ' + ', '.join(str(row[0]) for row in accepted))
            if len(accepted) == 1 and not pending:
                path, directory, sha, reports = accepted[0]
                output.mkdir(parents=True, exist_ok=True)
                archive = output / sha
                archive.mkdir(exist_ok=True)
                shutil.copy2(path, archive / path.name)
                if directory.exists():
                    shutil.copytree(directory, archive, dirs_exist_ok=True)
                if digest(archive / path.name) != sha:
                    raise ValueError('archive integrity failure')
                (archive / 'acceptance.json').write_text(json.dumps(dict(workload='complete', profiler='accepted',
                    source=str(path), sha256=sha, reports=reports), indent=2) + '\n')
                return reports, archive
        if time.monotonic() >= deadline:
            detail = '; '.join(Path(p).name + ': ' + why for p, why in failures.items())
            raise ValueError('capture awaiting review' + ('; incomplete writes: ' + ', '.join(pending) if pending else '') + ('; ' + detail if detail else '; no matching new capture'))
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['baseline', 'collect'])
    p.add_argument('--root', action='append', type=Path, default=[])
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--output', type=Path)
    p.add_argument('--human-complete', action='store_true')
    p.add_argument('--place')
    p.add_argument('--run', help='expected run identity when available in markers or capture metadata')
    p.add_argument('--marker', action='append', default=[])
    p.add_argument('--coverage', choices=['sample', 'full'], default='sample')
    p.add_argument('--min-frames', type=int, default=1)
    p.add_argument('--expected-frames', type=int)
    p.add_argument('--spike-ms', type=float, default=20)
    p.add_argument('--wait', type=float, default=5)
    p.add_argument('--node', default='node')
    p.add_argument('--select', type=Path, help='explicit resolution after ambiguous matches')
    a = p.parse_args(argv)
    try:
        roots = a.root or [Path.home()/'Library/Logs/Roblox', Path.home()/'Downloads']
        if a.action == 'baseline':
            a.baseline.parent.mkdir(parents=True, exist_ok=True)
            with a.baseline.open('x') as stream: json.dump(inventory(roots), stream)
            print('CAPTURE|baseline recorded'); return 0
        if not a.human_complete or not a.place or not a.marker or not a.output:
            raise ValueError('human completion, place, marker and archive output required')
        if not 0 <= a.wait <= 60 or a.min_frames < 1 or not math.isfinite(a.spike_ms) or a.spike_ms <= 0:
            raise ValueError('invalid capture bounds')
        if a.coverage == 'full' and (not a.expected_frames or a.expected_frames < 1):
            raise ValueError('expected frame count required')
        reports, archive = collect(json.loads(a.baseline.read_text()), roots, a.output, a.place, a.marker,
            a.coverage, a.min_frames, a.expected_frames, a.spike_ms, a.wait, a.node, a.select, a.run)
        print(render(reports)); print('CAPTURE|accepted|archive=' + str(archive)); return 0
    except (ValueError, OSError) as error:
        print('CAPTURE|awaiting-review|' + str(error)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
