"""Real stdlib children in separate process groups; no model or participant data."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from journey.process import supervise, process_table

class ProcessTests(unittest.TestCase):
    def test_timeout_kills_nested_new_session_grandchild_and_reaps_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'grandchild.py').write_text("import os,time,pathlib\npathlib.Path('grandchild.pid').write_text(str(os.getpid()))\ntime.sleep(30)\n")
            (root/'child.py').write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'grandchild.py'],start_new_session=True)\ntime.sleep(30)\n")
            (root/'parent.py').write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'child.py'],start_new_session=True)\ntime.sleep(30)\n")
            began=time.monotonic()
            runtime=supervise([sys.executable,str(root/'parent.py')],b'{}',cwd=root,env=os.environ.copy(),timeout_seconds=0.6)
            self.assertTrue(runtime['timedOut']);self.assertLess(time.monotonic()-began,4)
            pid=int((root/'grandchild.pid').read_text())
            for _ in range(40):
                record=process_table().get(pid)
                if record is None or record['state'].startswith('Z'):break
                time.sleep(0.025)
            self.assertTrue(record is None or record['state'].startswith('Z'))
            self.assertGreaterEqual(runtime['descendantsTerminated'],2)
    def test_short_process_completes_without_killing_unrelated_process(self):
        unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'],start_new_session=True)
        try:
            result=supervise([sys.executable,'-c','import sys;sys.stdin.buffer.read()'],b'{}',cwd=Path.cwd(),env=os.environ.copy(),timeout_seconds=2)
            self.assertFalse(result['timedOut']);self.assertEqual(result['workerExitCode'],0)
            self.assertIsNone(unrelated.poll())
        finally:unrelated.kill();unrelated.wait()

    def test_unexpected_root_exit_cleans_previously_tracked_orphan(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'child.py').write_text("import os,time,pathlib\npathlib.Path('child.pid').write_text(str(os.getpid()))\ntime.sleep(30)\n")
            (root/'parent.py').write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'child.py'],start_new_session=True)\ntime.sleep(0.3)\nraise SystemExit(7)\n")
            runtime=supervise([sys.executable,str(root/'parent.py')],b'{}',cwd=root,env=os.environ.copy(),timeout_seconds=2)
            self.assertEqual(runtime['workerExitCode'],7);self.assertTrue(runtime['cleanupConfirmed'])
            record=process_table().get(int((root/'child.pid').read_text()))
            self.assertTrue(record is None or record['state'].startswith('Z'))

    def test_identity_mismatch_is_never_signalled(self):
        from unittest.mock import patch
        from journey.process import _signal
        original={'pid':12345,'ppid':42,'started':'old','state':'S'}
        current={**original,'started':'different'}
        with patch('journey.process.os.kill') as kill:
            self.assertFalse(_signal(original,signal.SIGKILL,{12345:current},{12345:original}));kill.assert_not_called()

    def test_scan_failure_is_bounded_and_reports_cleanup_unconfirmed(self):
        from unittest.mock import patch
        from journey.process import CleanupUnconfirmed
        began=time.monotonic()
        with patch('journey.process.process_table',side_effect=CleanupUnconfirmed('cleanup_unconfirmed')):
            runtime=supervise([sys.executable,'-c','import time;time.sleep(30)'],b'{}',cwd=Path.cwd(),env=os.environ.copy(),timeout_seconds=1)
        self.assertFalse(runtime['cleanupConfirmed']);self.assertLess(time.monotonic()-began,2)

    def test_adapter_latches_unconfirmed_cleanup_in_private_root(self):
        from unittest.mock import patch
        from journey.adapter import OfflineAdapter
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);adapter=OfflineAdapter(root)
            runtime={'cleanupConfirmed':False,'tracked':[],'timedOut':True,'workerExitCode':-9}
            with patch('journey.process.supervise',return_value=runtime) as supervised:
                with self.assertRaises(Exception):adapter.assess(b'unit-nonspeech',{},9)
                self.assertEqual(supervised.call_count,1)
                with self.assertRaises(Exception):adapter.assess(b'unit-nonspeech',{},9)
                self.assertEqual(supervised.call_count,1)
            marker=root/'process-cleanup-blocked.json';self.assertTrue(marker.exists())
            self.assertEqual(marker.stat().st_mode&0o777,0o600)
            with self.assertRaises(Exception):OfflineAdapter(root).assert_cleanup()

    def test_explicit_cancellation_cleans_nested_worker_tree(self):
        import threading
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'child.py').write_text("import os,time,pathlib\npathlib.Path('cancel-child.pid').write_text(str(os.getpid()))\ntime.sleep(30)\n")
            (root/'parent.py').write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'child.py'],start_new_session=True)\ntime.sleep(30)\n")
            cancel=threading.Event();timer=threading.Timer(0.4,cancel.set);timer.start()
            try:runtime=supervise([sys.executable,str(root/'parent.py')],b'{}',cwd=root,env=os.environ.copy(),timeout_seconds=5,cancellation_event=cancel)
            finally:timer.cancel();timer.join()
            self.assertTrue(runtime['cancelled']);self.assertFalse(runtime['timedOut']);self.assertTrue(runtime['cleanupConfirmed'])
            record=process_table().get(int((root/'cancel-child.pid').read_text()))
            self.assertTrue(record is None or record['state'].startswith('Z'))

    def test_optional_failure_marker_write_cannot_forget_prelaunch_cleanup_intent(self):
        from unittest.mock import patch
        from journey.adapter import OfflineAdapter
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);adapter=OfflineAdapter(root)
            runtime={'cleanupConfirmed':False,'tracked':[],'timedOut':True,'workerExitCode':-9}
            with patch('journey.process.supervise',return_value=runtime),patch.object(adapter,'_block',side_effect=OSError('unit disk full')):
                with self.assertRaises(Exception):adapter.assess(b'unit-nonspeech',{},9)
            with self.assertRaises(Exception):OfflineAdapter(root).assert_cleanup()
            self.assertTrue((root/'process-cleanup-required.json').exists())

    def test_prelaunch_intent_write_failure_never_starts_subprocess(self):
        from unittest.mock import patch
        from journey.adapter import OfflineAdapter
        with tempfile.TemporaryDirectory() as directory:
            adapter=OfflineAdapter(Path(directory))
            with patch.object(adapter,'_write_marker',side_effect=OSError('unit disk full')),patch('journey.process.supervise') as supervised:
                with self.assertRaises(OSError):adapter.assess(b'unit-nonspeech',{},9)
                supervised.assert_not_called()

    def test_confirmed_cleanup_removes_intent_only_after_private_stage_is_removed(self):
        from unittest.mock import patch
        from journey.adapter import OfflineAdapter
        import json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);adapter=OfflineAdapter(root);stages=[]
            def completed(command,raw,**kwargs):
                stage=Path(command[-1]);stages.append(stage)
                self.assertTrue((root/'process-cleanup-required.json').exists())
                (stage/'unit-nested').mkdir(mode=0o700);(stage/'unit-nested/private.json').write_text('unit-only private sentinel')
                (stage/'result.json').write_text(json.dumps({'unitTestOnly':True}));(stage/'result.json').chmod(0o600)
                return {'cleanupConfirmed':True,'tracked':[],'timedOut':False,'workerExitCode':0,'cancelled':False}
            with patch('journey.process.supervise',side_effect=completed):
                self.assertEqual(adapter.assess(b'unit-nonspeech',{},9),{'unitTestOnly':True})
            self.assertTrue(all(not stage.exists() for stage in stages));self.assertFalse((root/'process-cleanup-required.json').exists())
            adapter.assert_cleanup()

    def test_worker_confines_frozen_recognition_runtime_to_owned_stage(self):
        from unittest.mock import patch
        from journey import worker
        from admission import adapter
        import base64,io,json,types
        with tempfile.TemporaryDirectory() as directory:
            stage=Path(directory).resolve();payload={'audioBase64':base64.b64encode(b'unit-nonspeech').decode(),'prompt':{},'ageYears':9}
            def assessed(*args,**kwargs):
                self.assertEqual(adapter.WORK,stage)
                return {'unitTestOnly':True}
            with patch.object(adapter,'WORK',adapter.WORK),patch.object(worker.admission,'assess',side_effect=assessed),patch.object(worker.sys,'stdin',types.SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))),patch.object(worker.sys,'argv',['worker',str(stage)]):
                worker.main()
            self.assertEqual(json.loads((stage/'result.json').read_bytes()),{'unitTestOnly':True})
            self.assertEqual((stage/'result.json').stat().st_mode&0o777,0o600)
