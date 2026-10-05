"""H02: Do collection boundaries reject invalid evidence and retain valid observations?
Stop when each changed boundary has a decisive saved-fixture result.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT/'tools/frame_census'))
import test_buffer as codec
import studio_output
import capture

RAW = b'HTB1\nR\tH02\tpass\t1\t0\t0\t-\n'


def viewer(place=12, marker='Harness/r/H/m/w/measurement', frames=3):
    return {'GeneralInfo': {'PlaceId': place}, 'ThreadClobbered': [False],
            'TimerInfo': [{'id': i, 'name': marker+'/'+str(i+1)} for i in range(frames)],
            'AggregateInfo': {'Frames': 9999},
            'Frames': [{'framestart': i*10, 'frameend': i*10+10, 'tt': [[1,0]],
                        'ti': [[i,i]], 'ts': [[i*10+1,i*10+3]], 'paused': False, 'incomplete': False} for i in range(frames)]}


class BufferTests(unittest.TestCase):
    def test_roundtrip_damage_truncation_conflict_and_prefix(self):
        raw = RAW + b'M\tm\tw\tscript\t2\t8000\t4000\t3000\t2\t0\t10000\nP\tm\tw\tscript\t1\t4000\nP\tm\tw\tscript\t2\t4000\n'
        lines = codec.encode_records(raw, 'CLIENT', 'Test', 'r')
        c = codec.Collector(('CLIENT','Test','r')); c.feed('\n'.join(lines+lines))
        result = c.finish()[0][1]
        self.assertEqual(result['metrics'][0]['spikes'], [(1,4000),(2,4000)])
        self.assertIn('average=4.000ms', codec.summary(c.finish()))
        for bad in (lines[0][:-2], lines[0][:-2]+'00', lines[0].replace('CLIENT|','SERVER|'), lines[0].replace('|BUF|1|','|BUF|2|')):
            c=codec.Collector(('CLIENT','Test','r')); c.feed(bad)
            with self.assertRaises(ValueError): c.finish()
        c=codec.Collector(); c.feed(lines[0]); c.feed(lines[0][:-2]+'00')
        with self.assertRaisesRegex(ValueError, 'conflicting'): c.finish()

    def test_multichunk_reordering_missing_output_rotation(self):
        rows=[]
        for i in range(25): rows.append(f'M\tm{i}\tw\tscript\t1\t1\t1\t2\t0\t0\t1\n'.encode())
        lines=codec.encode_records(RAW+b''.join(rows), 'CLIENT','Test','r')
        self.assertGreater(len(lines),1)
        c=codec.Collector(); c.feed('\n'.join(reversed(lines))); self.assertEqual(len(c.finish()[0][1]['metrics']),25)
        c=codec.Collector(); c.feed(lines[0])
        with self.assertRaisesRegex(ValueError, 'incomplete'): c.finish()
        with self.assertRaisesRegex(ValueError, 'missing'): codec.Collector().finish()
        with tempfile.TemporaryDirectory() as temp:
            first=studio_output.snapshot('studio:x',lines[0],cache=Path(temp))
            second=studio_output.snapshot('studio:x','\n'.join(lines[1:])+'\nError: unrelated failure',first['artifact'],['BUF'],cache=Path(temp))
            c=codec.Collector(); c.feed('\n'.join(second['transport']))
            self.assertEqual(c.finish()[0][1]['passed'],1)
            self.assertEqual(second['continuity'],'reset-or-rotation')
            self.assertIn('unrelated failure',second['errors'][0])

    def test_invalid_schema_counts_spikes_and_missing_values(self):
        for raw in (RAW.replace(b'HTB1',b'HTB2'), RAW[:-1], RAW.replace(b'pass\t1',b'pass\t0'),
                    RAW+b'M\tm\tw\tscript\t1\t2\t1\t1\t0\t0\t2\n',
                    RAW+b'M\tm\tw\tscript\t1\t2\t2\t1\t1\t0\t2\n',
                    RAW+b'M\tm\tw\tframe\t1\t2\t2\t1\t0\t0\t2\n',
                    RAW+b'M\tm\tw\tscript\t1\t2\t2\t1\t0\t0\t2\n'):
            with self.assertRaises(ValueError): codec.decode(raw)
        self.assertEqual(codec.historical('TEST|{"status":"pass","passed":1,"failed":0,"skipped":0}')[0]['passed'],1)
        self.assertEqual(codec.historical('{"status":"pass","passed":1,"failed":0,"skipped":0}')[0]['passed'],1)
        with self.assertRaises(ValueError): codec.historical('{"Version":2}')

    def test_live_cli_decodes_before_limits_and_keeps_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            log=Path(temp)/'log.txt'; log.write_text(codec.encode_records(RAW,'CLIENT','Test','r')[0]+'\nError: retained')
            snapshot = studio_output.snapshot
            def temporary_snapshot(*args, **kwargs):
                return snapshot(*args, **kwargs, cache=Path(temp)/'cache')
            with mock.patch.object(studio_output, 'snapshot', side_effect=temporary_snapshot), contextlib.redirect_stdout(io.StringIO()) as output:
                status=studio_output.main(['--input',str(log),'--side','CLIENT','--script','Test','--run','r','--max-chars','1','--contains','nomatch'])
            self.assertEqual(status,0)
            self.assertIn('H02|pass',output.getvalue())
            self.assertIn('Error: retained',output.getvalue())
            self.assertNotIn('|BUF|',output.getvalue())


class CaptureTests(unittest.TestCase):
    marker='Harness/r/H/m/w/measurement'

    def test_partial_full_coverage_wrong_identity_and_corrupt_arrays(self):
        data=viewer()
        report=capture.analyze(data,12,[self.marker],'full',3,3)[0]
        self.assertEqual(report['scope_average_ms'],2)
        self.assertEqual(report['frame_average_ms'],10)
        with self.assertRaisesRegex(ValueError,'partial capture'): capture.analyze(data,12,[self.marker],'full',1,4)
        for place,marker in ((13,self.marker),(12,'Harness/other/H/m/w/measurement')):
            with self.assertRaises(ValueError): capture.analyze(data,place,[marker],'sample',1)
        data['Frames'][1]['incomplete']=True
        with self.assertRaises(ValueError): capture.analyze(data,12,[self.marker],'sample',1)
        data=viewer(); data['Frames'][0]['tt']=[[0]]; data['Frames'][0]['ti']=[[0]]; data['Frames'][0]['ts']=[[3]]
        with self.assertRaisesRegex(ValueError,'partial workload'): capture.analyze(data,12,[self.marker],'sample',1)

    def test_newest_wrong_file_ambiguous_and_incomplete_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); out=root/'archive'
            first=root/'one-viewer-data.json'; first.write_text(json.dumps(viewer()))
            baseline=capture.inventory([root])
            match=root/'two-viewer-data.json'; match.write_text(json.dumps(viewer()))
            wrong=root/'wrong-viewer-data.json'; wrong.write_text(json.dumps(viewer(place=13)))
            reports,archive=capture.collect(baseline,[root],out,12,[self.marker],wait=1)
            self.assertEqual(reports[0]['frames'],3)
            self.assertTrue((archive/match.name).is_file())
            other=root/'another-viewer-data.json'; other.write_text(json.dumps(viewer()))
            with self.assertRaisesRegex(ValueError,'ambiguous'): capture.collect(baseline,[root],out,12,[self.marker],wait=1)
            other.unlink(); match.write_text('{')
            with self.assertRaisesRegex(ValueError,'awaiting review'): capture.collect(baseline,[root],out,12,[self.marker],wait=0.6)

    def test_native_export_reader_uses_event_durations(self):
        with tempfile.TemporaryDirectory() as temp:
            stem=Path(temp)/'native'
            stem.with_suffix('.csv').write_text('frames,60\ngroup,average,max,total\nWork,999,999,999\nThread Name: Main\nGroup Name,Marker Name,Begin,End,Labels\nWork,Scope,1,3,\nWork,Scope,4,6,\n')
            Path(str(stem)+'_counters.csv').write_text('Name,Value,Limit\nCounter,1,2\n')
            Path(str(stem)+'_summary.json').write_text(json.dumps({'num_frames':128,'cpu_time_median':999,'general_info':{'PlaceId':12}}))
            result=subprocess.run([sys.executable,str(ROOT/'tools/harness.py'),'profile','frames',str(stem),'--place','12'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            self.assertIn('average=2.000ms',result.stdout)
            self.assertNotIn('999',result.stdout)

    def test_capture_spikes_separate_and_overflow(self):
        data=viewer(frames=300)
        r=capture.analyze(data,12,[self.marker],'full',1,300,spike_ms=5)[0]
        self.assertEqual(len(r['spikes']),256); self.assertEqual(r['overflow'],44)
        self.assertEqual(r['frame_average_ms'],10)

    def test_saved_event_window_ignores_non_time_labels_and_rolling_totals(self):
        data=json.loads((ROOT/'tests/fixtures/profiler-window.json').read_text())
        reports=capture.analyze(data,87497640614278,['Spatial/B08/box'],'sample',3)
        self.assertEqual(reports[0]['frames'],3)
        self.assertGreater(reports[0]['scope_average_ms'],0)
        data['GeneralInfo']['RunId']='wrong'
        with self.assertRaisesRegex(ValueError,'wrong run'):
            capture.analyze(data,87497640614278,['Spatial/B08/box'],'sample',3,run='wanted')

    def test_incomplete_candidate_prevents_premature_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'good-viewer-data.json').write_text(json.dumps(viewer()))
            (root/'writing-viewer-data.json').write_text('{')
            with self.assertRaisesRegex(ValueError,'incomplete writes'):
                capture.collect({},[root],root/'archive',12,[self.marker],wait=0.6)

    def test_adapter_rejects_unsupported_and_timeout(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'dump.html';source.write_text('<html>unsupported</html>')
            with self.assertRaises(ValueError): capture.export_html(source,root/'out')
            with mock.patch.object(subprocess,'run',side_effect=subprocess.TimeoutExpired('node',60)):
                with self.assertRaises(subprocess.TimeoutExpired): capture.export_html(source,root/'out2')


class ScaffoldTests(unittest.TestCase):
    def test_test_scaffold_one_side_support_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/'Place1.project.json'
            project.write_text(json.dumps({'tree':{'StarterPlayer':{'StarterPlayerScripts':{'Tests':{'$path':'tests/Place1/client'}}}}}))
            command=[sys.executable,str(ROOT/'tools/harness.py'),'--root',temp,'scaffold','module','--test','Fix.H02','--place','Place1','--side','client']
            result=subprocess.run(command,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            test=Path(temp)/'tests/Place1/client/Fix.H02.client.luau'
            before=test.read_bytes()
            support=json.loads(project.read_text())['tree']['StarterPlayer']['StarterPlayerScripts']['Tests']['TestSupport']['$path']
            self.assertTrue((Path(temp)/support/'Runner.luau').is_file())
            self.assertFalse((test.parent.parent/'server').exists())
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(test.read_bytes(),before)


if __name__=='__main__': unittest.main()
