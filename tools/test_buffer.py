"""HTB1 buffer transport. Shared by test, debug and optimization collection."""
import argparse
import json
import math
from pathlib import Path
import re
import zlib

LIMIT = 65536
CHUNK = 512
TOKEN = re.compile(r'^[A-Za-z0-9_.:/-]{1,96}$')
RECORD = re.compile(r'(SERVER|CLIENT)\|([^|\s]+)\|BUF\|([^\s]+)')
KINDS = {'script', 'scheduling', 'setup', 'teardown'}
STATUSES = {'pass', 'fail', 'cancelled', 'timeout', 'unrun'}


def token(value):
    if not TOKEN.fullmatch(value):
        raise ValueError('invalid identity')
    return value


def integer(value, minimum=0):
    if not re.fullmatch(r'0|[1-9][0-9]*', value):
        raise ValueError('invalid integer')
    number = int(value)
    if not minimum <= number <= 2**53 - 1:
        raise ValueError('integer out of range')
    return number


def reason(value):
    if len(value) > 160 or any(ord(c) < 32 or ord(c) > 126 or c == '|' for c in value):
        raise ValueError('invalid reason')
    return value


def decode(raw):
    if not 1 <= len(raw) <= LIMIT:
        raise ValueError('payload limit')
    text = raw.decode('ascii')
    lines = text.splitlines()
    if not text.endswith('\n') or not lines or lines.pop(0) != 'HTB1':
        raise ValueError('unsupported or truncated buffer')
    if not lines:
        raise ValueError('missing result')
    row = lines.pop(0).split('\t')
    if len(row) != 7 or row[0] != 'R' or row[2] not in STATUSES:
        raise ValueError('invalid result')
    result = dict(id=token(row[1]), status=row[2], passed=integer(row[3]),
                  failed=integer(row[4]), skipped=integer(row[5]), reason=reason(row[6]), metrics=[])
    if result['status'] == 'pass' and (result['failed'] or not result['passed']):
        raise ValueError('empty or failed pass')
    if result['status'] != 'pass' and row[6] == '-':
        raise ValueError('missing failure reason')
    groups = {}
    for line in lines:
        row = line.split('\t')
        if row[0] == 'M' and len(row) == 11:
            method, workload, kind = token(row[1]), token(row[2]), row[3]
            key = (method, workload, kind)
            if kind not in KINDS or key in groups or len(groups) >= 32:
                raise ValueError('conflicting metric')
            count, total, maximum, threshold, spikes, overflow, window = map(integer, row[4:])
            if not count or not threshold or maximum > total or total > maximum * count or spikes > count or overflow > spikes:
                raise ValueError('invalid metric totals')
            if (maximum > threshold) != (spikes > 0) or (spikes and total < maximum + (spikes-1)*(threshold+1)) or total > spikes*maximum + (count-spikes)*min(maximum, threshold):
                raise ValueError('inconsistent spike totals')
            group = dict(method=method, workload=workload, kind=kind, count=count, total_us=total,
                         max_us=maximum, threshold_us=threshold, spike_count=spikes, overflow=overflow,
                         window_us=window, spikes=[])
            groups[key] = group
            result['metrics'].append(group)
        elif row[0] == 'P' and len(row) == 6:
            key = tuple(row[1:4])
            if key not in groups:
                raise ValueError('spike before metric')
            group = groups[key]
            index, duration = integer(row[4], 1), integer(row[5])
            if index > group['count'] or duration <= group['threshold_us'] or duration > group['max_us'] or any(p[0] == index for p in group['spikes']):
                raise ValueError('invalid spike')
            group['spikes'].append((index, duration))
            if len(group['spikes']) > 256:
                raise ValueError('spike storage limit')
        else:
            raise ValueError('unsupported payload row')
    for group in groups.values():
        if sum(p[1] for p in group['spikes']) > group['total_us']:
            raise ValueError('spike durations exceed total')
        if len(group['spikes']) + group['overflow'] != group['spike_count']:
            raise ValueError('incomplete spikes')
    return result


def encode_records(raw, side, script, run):
    """Reference encoder for transport fixtures; runtime encoder uses a Luau buffer."""
    decode(raw)
    if side not in {'SERVER', 'CLIENT'}:
        raise ValueError('invalid side')
    token(script); token(run)
    checksum = zlib.adler32((side + '|' + script + '|' + run + '\0').encode() + raw)
    count = math.ceil(len(raw) / CHUNK)
    return [f'{side}|{script}|BUF|1|{run}|{i+1}|{count}|{len(raw)}|{checksum:08x}|{raw[i*CHUNK:(i+1)*CHUNK].hex()}' for i in range(count)]


class Collector:
    def __init__(self, expected=None):
        self.expected = expected  # (side, script, run); mandatory for acceptance
        self.groups = {}
        self.errors = []

    def feed(self, console):
        for line in console.splitlines():
            match = RECORD.search(line)
            if not match:
                if '|BUF|' in line:
                    self.errors.append('malformed transport record')
                continue
            side, script, body = match.groups()
            try:
                fields = body.split('|')
                if len(fields) != 7:
                    raise ValueError('truncated transport')
                version, run, seq, count, size, checksum, payload = fields
                if self.expected and (script, run) != self.expected[1:]:
                    continue
                if self.expected and side != self.expected[0]:
                    raise ValueError('incorrect runtime prefix')
                if version != '1':
                    raise ValueError('unsupported transport')
                token(script); token(run)
                seq, count, size = integer(seq, 1), integer(count, 1), integer(size, 1)
                if size > LIMIT or count != math.ceil(size / CHUNK) or seq > count:
                    raise ValueError('invalid chunk bounds')
                if len(payload) > CHUNK * 2 or not re.fullmatch('[0-9a-f]{8}', checksum) or not re.fullmatch('(?:[0-9a-f]{2})+', payload):
                    raise ValueError('invalid transport encoding')
                chunk = bytes.fromhex(payload)
                if len(chunk) != min(CHUNK, size - (seq-1)*CHUNK):
                    raise ValueError('truncated chunk')
                key = (side, script, run)
                if key not in self.groups and len(self.groups) >= 64:
                    raise ValueError('record limit')
                group = self.groups.setdefault(key, {'meta': (count, size, checksum), 'chunks': {}})
                if group['meta'] != (count, size, checksum) or (seq in group['chunks'] and group['chunks'][seq] != chunk):
                    raise ValueError('conflicting transport')
                group['chunks'][seq] = chunk
            except (ValueError, UnicodeError) as error:
                self.errors.append(str(error))
        self.errors = list(dict.fromkeys(self.errors))[:20]

    def finish(self):
        if self.errors:
            raise ValueError('; '.join(self.errors))
        if not self.groups:
            raise ValueError('missing output')
        results = []
        for key, group in self.groups.items():
            count, size, checksum = group['meta']
            if len(group['chunks']) != count:
                raise ValueError('incomplete buffer')
            raw = b''.join(group['chunks'][i] for i in range(1, count+1))
            actual = zlib.adler32(('|'.join(key) + '\0').encode() + raw)
            if len(raw) != size or f'{actual:08x}' != checksum:
                raise ValueError('buffer integrity failure')
            results.append((key, decode(raw)))
        return results


def summary(records):
    output = []
    for (side, script, _run), result in records:
        prefix = f'{side}|{script}|'
        output.append(prefix + f"{result['id']}|{result['status']}|passed={result['passed']} failed={result['failed']} skipped={result['skipped']}" + (f"|{result['reason']}" if result['reason'] != '-' else ''))
        for m in result['metrics']:
            output.append(prefix + f"{m['method']}/{m['workload']}|{m['kind']}|average={m['total_us']/m['count']/1000:.3f}ms|count={m['count']}|window={m['window_us']/1000:.3f}ms|spikes={m['spike_count']} max={m['max_us']/1000:.3f}ms overflow={m['overflow']}")
    return '\n'.join(output)


def historical(text):
    """Read historical TEST JSON without routing profiler exports through this codec."""
    stripped = text.strip()
    if stripped.startswith('{'):
        rows = [json.loads(stripped)]
    else:
        rows = [json.loads(line.split('TEST|', 1)[1]) for line in text.splitlines() if 'TEST|' in line]
    if len(rows) > 64:
        raise ValueError('historical result limit')
    for value in rows:
        if not isinstance(value, dict) or value.get('status') not in {'pass', 'fail', 'unrun'}:
            raise ValueError('unsupported historical result')
        for key in ('passed', 'failed', 'skipped'):
            integer(str(value[key]))
        if value['status'] == 'pass' and (not value['passed'] or value['failed']):
            raise ValueError('invalid historical pass')

    if not rows:
        raise ValueError('missing historical results')
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--side', choices=['SERVER', 'CLIENT'])
    p.add_argument('--script'); p.add_argument('--run')
    p.add_argument('--historical', action='store_true')
    a = p.parse_args(argv)
    try:
        text = a.input.read_text()
        if a.historical:
            rows = historical(text)
            for r in rows:
                print(f"HISTORICAL|legacy-status={r['status']}|passed={r['passed']} failed={r['failed']} skipped={r['skipped']}" + ("|" + reason(r["reason"]) if r.get("reason") else ""))
            return 0 if all(r['status'] == 'pass' for r in rows) else 2
        if not all((a.side, a.script, a.run)):
            raise ValueError('side, script and run required')
        c = Collector((a.side, a.script, a.run)); c.feed(text)
        results = c.finish(); print(summary(results))
        return 0 if all(r['status'] == 'pass' for _, r in results) else 2
    except (OSError, ValueError, KeyError) as e:
        print('RESULT|rejected|' + str(e)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
