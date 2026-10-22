"""Owned trusted-worker supervision; real stdlib processes, no model/audio/sensors."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from mobile_admission import process


class ProcessTests(unittest.TestCase):
    def test_equivalent_start_stamp_padding_does_not_change_owned_identity(self):
        original=process.process_table;calls=[0]
        def padded(timeout_seconds=0.4):
            records=original(timeout_seconds=timeout_seconds);calls[0]+=1
            for record in records.values():record['started']=record['started'].strip()+(' ' if calls[0]%2 else '    ')
            return records
        with patch.object(process,'process_table',side_effect=padded):
            runtime=process.supervise([sys.executable,'-c','import sys,time;sys.stdin.buffer.read();time.sleep(0.15)'],b'{}',cwd=Path.cwd(),env=os.environ.copy(),timeout_seconds=2)
        self.assertTrue(runtime['cleanupConfirmed']);self.assertEqual(runtime['workerExitCode'],0)
        self.assertFalse(runtime['timedOut'])

    def test_persistent_scanner_failure_retains_fixed_phase_code_and_identity(self):
        original=process.process_table;calls=[0]
        def failed(timeout_seconds=0.4):
            calls[0]+=1
            if calls[0]>1:raise process.CleanupUnconfirmed('scan_failed')
            return original(timeout_seconds=timeout_seconds)
        with patch.object(process,'process_table',side_effect=failed):
            runtime=process.supervise([sys.executable,'-c','import time;time.sleep(30)'],b'{}',cwd=Path.cwd(),env=os.environ.copy(),timeout_seconds=2)
        self.assertFalse(runtime['cleanupConfirmed']);self.assertFalse(runtime['timedOut'])
        self.assertEqual(runtime['cleanupFailurePhase'],'monitor');self.assertEqual(runtime['cleanupFailureCode'],'scan_failed')
        self.assertTrue(runtime['tracked']);self.assertGreaterEqual(runtime['scanCount'],2)
        self.assertGreaterEqual(runtime['scanRetries'],1)
        self.assertNotIn('argv',runtime);self.assertNotIn('env',runtime)

    def test_changed_start_identity_fails_closed(self):
        original=process.process_table;calls=[0]
        def changed(timeout_seconds=0.4):
            records=original(timeout_seconds=timeout_seconds);calls[0]+=1
            if calls[0]>1:
                for record in records.values():record['started']='changed identity'
            return records
        with patch.object(process,'process_table',side_effect=changed):
            runtime=process.supervise([sys.executable,'-c','import time;time.sleep(30)'],b'{}',cwd=Path.cwd(),env=os.environ.copy(),timeout_seconds=2)
        self.assertFalse(runtime['cleanupConfirmed'])
        self.assertTrue(runtime['supervisionFailed'])
        self.assertEqual(runtime['cleanupFailureCode'],'root_identity_changed')

    def test_scan_timeout_is_capped_by_remaining_deadline(self):
        budgets=[]
        def slow(timeout_seconds=0.4):
            budgets.append(timeout_seconds);time.sleep(timeout_seconds)
            raise process.CleanupUnconfirmed('scan_timeout')
        metrics={'scanCount':0,'scanElapsedSeconds':0.0,'scanMaximumSeconds':0.0,'scanRetries':0}
        began=time.monotonic()
        with patch.object(process,'process_table',side_effect=slow):
            with self.assertRaises(process.CleanupUnconfirmed):process._scan(began+0.08,metrics)
        self.assertLessEqual(budgets[0],0.08)
        self.assertLess(time.monotonic()-began,0.25)
        self.assertEqual(metrics['scanRetries'],0)

    def test_one_transient_scan_retry_preserves_normal_completion(self):
        original=process.process_table;calls=[0]
        def transient(timeout_seconds=0.4):
            calls[0]+=1
            if calls[0]==2:raise process.CleanupUnconfirmed('scan_timeout')
            return original(timeout_seconds=timeout_seconds)
        with patch.object(process,'process_table',side_effect=transient):
            runtime=process.supervise([sys.executable,'-c','import sys,time;sys.stdin.buffer.read();time.sleep(.15)'],b'{}',cwd=Path.cwd(),env=os.environ.copy(),timeout_seconds=2)
        self.assertTrue(runtime['cleanupConfirmed']);self.assertEqual(runtime['workerExitCode'],0)
        self.assertFalse(runtime['supervisionFailed']);self.assertIsNone(runtime['cleanupFailurePhase'])
        self.assertEqual(runtime['scanRetries'],1)

    def test_monitor_failure_is_retained_even_when_owned_tree_cleanup_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path=Path(directory)/'child-pid'
            script='import pathlib,subprocess,sys,time;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],start_new_session=True);pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(30)'
            original=process.process_table;failures=[0];armed=[False]
            def transient_pair(timeout_seconds=0.4):
                if armed[0] and failures[0]<2:
                    failures[0]+=1;raise process.CleanupUnconfirmed('scan_failed')
                table=original(timeout_seconds=timeout_seconds)
                if pid_path.exists() and int(pid_path.read_text()) in table:armed[0]=True
                return table
            with patch.object(process,'process_table',side_effect=transient_pair):
                runtime=process.supervise([sys.executable,'-c',script,str(pid_path)],b'{}',cwd=Path.cwd(),env=os.environ.copy(),timeout_seconds=2)
            self.assertTrue(runtime['cleanupConfirmed']);self.assertTrue(runtime['supervisionFailed'])
            self.assertEqual(runtime['cleanupFailurePhase'],'monitor');self.assertEqual(runtime['cleanupFailureCode'],'scan_failed')
            child=int(pid_path.read_text());record=original().get(child)
            self.assertTrue(record is None or record['state'].startswith('Z'))
            self.assertIn(child,{row['pid'] for row in runtime['tracked']})
            self.assertTrue(all(row['pid'] in {r['pid'] for r in runtime['tracked']} for row in runtime['lastObserved']))

    def test_nested_separate_sessions_are_gone_after_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path=Path(directory)/'grandchild-pid'
            child='import pathlib,subprocess,sys,time;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],start_new_session=True);pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(30)'
            root='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]],start_new_session=True);time.sleep(30)'
            runtime=process.supervise([sys.executable,'-c',root,child,str(pid_path)],b'{}',cwd=Path.cwd(),env=os.environ.copy(),timeout_seconds=1)
            self.assertTrue(runtime['timedOut']);self.assertTrue(runtime['cleanupConfirmed'])
            self.assertGreaterEqual(len(runtime['tracked']),3)
            current=process.process_table()
            for row in runtime['tracked']:
                record=current.get(row['pid'])
                self.assertTrue(not process._same(record,row) or record['state'].startswith('Z'))

    def test_changed_identity_is_never_signalled(self):
        owned={'pid':123,'ppid':42,'state':'S','started':'original'}
        foreign={**owned,'started':'different'}
        with patch.object(process.os,'kill') as kill:
            self.assertFalse(process._signal(owned,process.signal.SIGKILL,{123:foreign},{123:owned}))
        kill.assert_not_called()

    def test_root_exit_still_cleans_already_tracked_surviving_child(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path=Path(directory)/'child-pid'
            script='import pathlib,subprocess,sys,time;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],start_new_session=True);pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(.2)'
            runtime=process.supervise([sys.executable,'-c',script,str(pid_path)],b'{}',cwd=Path.cwd(),env=os.environ.copy(),timeout_seconds=2)
            self.assertEqual(runtime['workerExitCode'],0);self.assertTrue(runtime['cleanupConfirmed'])
            child=int(pid_path.read_text());record=process.process_table().get(child)
            self.assertTrue(record is None or record['state'].startswith('Z'))
            self.assertIn(child,{row['pid'] for row in runtime['tracked']})

    def test_malformed_scan_is_not_retried_and_expired_scan_never_runs(self):
        metrics={'scanCount':0,'scanElapsedSeconds':0.0,'scanMaximumSeconds':0.0,'scanRetries':0}
        with patch.object(process,'process_table',side_effect=process.CleanupUnconfirmed('scan_format_invalid')) as scan:
            with self.assertRaises(process.CleanupUnconfirmed):process._scan(time.monotonic()+1,metrics)
            self.assertEqual(scan.call_count,1);self.assertEqual(metrics['scanRetries'],0)
        with patch.object(process,'process_table') as scan:
            with self.assertRaises(process.CleanupUnconfirmed):process._scan(time.monotonic()-1,metrics)
            scan.assert_not_called()
