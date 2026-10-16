"""Generated-only worker ownership regressions; no model or research data access."""
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from consumer_assessment import bridge
from consumer_assessment.service import LocalServer
from consumer_assessment.test_bridge import raw, request


PARENT = r'''
import json, os, pathlib, subprocess, sys, time
stage, fixture, mode = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
child = None
child_identity = None
deadline = time.monotonic()+3
if mode != 'clean':
    child = subprocess.Popen([sys.executable, str(fixture/'child.py'), str(stage)])
    while not (stage/'child-ready.json').exists():
        if time.monotonic() > deadline: sys.exit(12)
        time.sleep(.005)
    child_identity = json.loads((stage/'child-ready.json').read_text())
(stage/'parent-ready.tmp').write_text(json.dumps({'pid':os.getpid(), 'pgid':os.getpgrp(),
    'child':child_identity}))
os.replace(stage/'parent-ready.tmp',stage/'parent-ready.json')
while not (stage/'proceed').exists():
    if time.monotonic() > deadline: sys.exit(13)
    time.sleep(.005)
if mode in ('success','clean'):
    req = json.loads((stage/'request.json').read_text())
    result = {'targets':[{**t,'subjectiveCorpusRatingProbabilities':[.1,.2,.7]}
                         for t in req['prompt']['targets']],
              'model':{'id':'ages-6-12-research-mixture','manifestSha256':sys.argv[4]}}
    (stage/'result.json').write_text(json.dumps(result))
    sys.exit(0)
if mode == 'crash': sys.exit(7)
time.sleep(8)
'''
CHILD = r'''
import json, os, pathlib, sys, time
stage = pathlib.Path(sys.argv[1])
(stage/'child-ready.tmp').write_text(json.dumps({'pid':os.getpid(), 'pgid':os.getpgrp()}))
os.replace(stage/'child-ready.tmp',stage/'child-ready.json')
time.sleep(8)
'''


def process_row(pid):
    result = subprocess.run(['/bin/ps','-p',str(pid),'-o','pgid=,stat=,command='],
                            capture_output=True,timeout=.5)
    if result.returncode == 1 and not result.stdout.strip(): return None
    result.check_returncode()
    fields = result.stdout.decode().strip().split(None,2)
    if len(fields) != 3: raise AssertionError('unreadable process identity')
    return int(fields[0]),fields[1],fields[2]


class GeneratedWorker:
    """Independent finite fixtures, with barriers and exact cleanup identities."""
    def __init__(self, root, mode):
        self.root, self.mode = Path(root),mode
        self.fixture = self.root/'fixture'; self.fixture.mkdir()
        (self.fixture/'parent.py').write_text(PARENT)
        (self.fixture/'child.py').write_text(CHILD)
        self.scratch = self.root/'scratch'; self.scratch.mkdir()
        self.processes, self.evidence, self.children = [],[],{}

    def launch(self, stage, env):
        process = subprocess.Popen([sys.executable,str(self.fixture/'parent.py'),str(stage),
                                    str(self.fixture),self.mode,bridge.MANIFEST_SHA],
                                   env=env,start_new_session=True,stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.processes.append((process,stage))
        deadline = time.monotonic()+3
        while not (stage/'parent-ready.json').exists():
            if (stage/'child-ready.json').exists():
                self.children[process.pid] = json.loads((stage/'child-ready.json').read_text())
            if time.monotonic() > deadline: raise AssertionError('fixture start barrier timed out')
            time.sleep(.005)
        evidence = json.loads((stage/'parent-ready.json').read_text())
        if evidence['pid'] != process.pid or evidence['pgid'] != process.pid:
            raise AssertionError('fixture leader identity mismatch')
        if evidence['child'] is not None:
            if evidence['child']['pgid'] != process.pid:
                raise AssertionError('fixture child group mismatch')
            self.children[process.pid] = evidence['child']
        elif self.mode != 'clean':
            raise AssertionError('fixture child missing')
        self.evidence.append(evidence)
        (stage/'proceed').touch()
        return process

    def close(self):
        # Does not use bridge helpers or mocks. Keep a still-owned leader pinned
        # while signalling its group; after a reap, only signal an identified
        # fixture child whose unique command path still matches this fixture.
        for process, stage in self.processes:
            if process.returncode is None:
                try:
                    os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                except ChildProcessError:
                    pass
                else:
                    table = subprocess.run(['/bin/ps','-axo','pid=,pgid=,stat='],
                                           capture_output=True,timeout=.5,check=True)
                    active = any(int(group) == process.pid and not state.startswith('Z')
                                 for pid,group,state in (line.split() for line in table.stdout.decode().splitlines()))
                    if active:
                        try: os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError: pass
            child = self.children.get(process.pid)
            if child is not None:
                row = process_row(child['pid'])
                if row and not row[1].startswith('Z'):
                    if row[0] != process.pid or str(self.fixture/'child.py') not in row[2]:
                        raise AssertionError('fixture child identity changed; refusing signal')
                    os.kill(child['pid'],signal.SIGKILL)
            process.wait(timeout=2)
        for child in self.children.values():
            deadline = time.monotonic()+2
            while True:
                row = process_row(child['pid'])
                if row is None or row[1].startswith('Z'): break
                if time.monotonic() > deadline: raise AssertionError('fixture child remains active')
                time.sleep(.01)


class WorkerLifecycleTests(unittest.TestCase):
    def run_fixture(self, mode, expected):
        with tempfile.TemporaryDirectory() as temp:
            fixture = GeneratedWorker(temp,mode)
            try:
                with patch.object(bridge,'TEMP_ROOT',fixture.scratch), \
                     patch.object(bridge,'_launch_worker',side_effect=fixture.launch), \
                     patch.object(bridge,'TIMEOUT_SECONDS',.15 if mode == 'timeout' else 2):
                    result = bridge.assess(raw(request()))
                self.assertEqual(result['outcome'],expected)
                self.assertEqual(result['reason'],{'success':None,'clean':None,'crash':'inference_failed','timeout':'timeout'}[mode])
                self.assertEqual(len(fixture.evidence),1)
                evidence = fixture.evidence[0]
                if evidence['child'] is not None:
                    self.assertEqual(evidence['child']['pgid'],evidence['pid'])
                    row = process_row(evidence['child']['pid'])
                    self.assertTrue(row is None or row[1].startswith('Z'),row)
                self.assertIsNone(process_row(evidence['pid']))
                self.assertEqual(list(fixture.scratch.iterdir()),[])
                self.assertIsNotNone(fixture.processes[0][0].returncode)
            finally: fixture.close()

    def test_normal_exit_drains_live_child_before_processed_result(self):
        self.run_fixture('success','processed')

    def test_clean_leader_without_child_returns_processed(self):
        self.run_fixture('clean','processed')

    def test_crashed_leader_drains_live_child_before_failure(self):
        self.run_fixture('crash','unavailable')

    def test_timeout_drains_leader_and_live_child(self):
        self.run_fixture('timeout','unavailable')

    def test_prelaunch_failure_removes_private_scratch(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(bridge,'TEMP_ROOT',Path(temp)), \
                 patch.object(bridge,'_launch_worker',side_effect=OSError('private launch detail')):
                result = bridge.assess(raw(request()))
            self.assertEqual(result['reason'],'inference_failed')
            self.assertEqual(list(Path(temp).iterdir()),[])
            self.assertNotIn('private launch detail',json.dumps(result))

    def test_inspection_uncertainty_escapes_assess_and_retains_scratch(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = GeneratedWorker(temp,'success')
            failure = None
            try:
                with patch.object(bridge,'TEMP_ROOT',fixture.scratch), \
                     patch.object(bridge,'_launch_worker',side_effect=fixture.launch), \
                     patch.object(bridge,'_active_group_members',side_effect=TimeoutError('private inspection detail')):
                    with self.assertRaises(bridge.CleanupUnconfirmed) as caught:
                        bridge.assess(raw(request()))
                    failure = caught.exception
                self.assertEqual(failure.directory,fixture.processes[0][1])
                self.assertTrue((failure.directory/'request.json').exists())
                self.assertIs(failure.process,fixture.processes[0][0])
                self.assertIsNone(failure.process.returncode)
                # The zombie is still ours to reap, so its PID/PGID is pinned.
                self.assertIsNotNone(os.waitid(os.P_PID,failure.process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT))
                self.assertEqual(str(failure),'worker cleanup unconfirmed')
            finally: fixture.close()

    def check_http_uncertainty(self, seam):
        with tempfile.TemporaryDirectory() as temp:
            fixture = GeneratedWorker(temp,'success')
            with LocalServer(0) as server:
                thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01}); thread.start()
                def send(method,path,data=None):
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=4)
                    try:
                        headers={'Content-Type':'application/json'} if data is not None else {}
                        conn.request(method,path,body=data,headers=headers)
                        response=conn.getresponse()
                        return response.status,json.loads(response.read())
                    finally: conn.close()
                if seam == 'inspect':
                    failure_patch=patch.object(bridge,'_active_group_members',side_effect=TimeoutError('private inspection detail'))
                elif seam == 'terminate':
                    failure_patch=patch.object(bridge.os,'killpg',side_effect=PermissionError('private signal detail'))
                else:
                    failure_patch=patch.object(bridge.shutil,'rmtree',side_effect=OSError('private cleanup detail'))
                try:
                    with patch.object(bridge,'TEMP_ROOT',fixture.scratch), \
                         patch.object(bridge,'_launch_worker',side_effect=fixture.launch) as launch, \
                         failure_patch:
                        with self.assertRaises(http.client.RemoteDisconnected):
                            send('POST','/v1/assessment',raw(request()))
                        self.assertIsInstance(server.cleanup_failure,bridge.CleanupUnconfirmed)
                        self.assertTrue(server.cleanup_failure.directory.exists())
                        status,body=send('GET','/health')
                        self.assertEqual(status,503); self.assertFalse(body['available'])
                        status,body=send('POST','/v1/assessment',raw(request()))
                        self.assertEqual(status,503); self.assertEqual(body['reason'],'model_unavailable')
                        self.assertEqual(body['outcome'],'unavailable'); self.assertEqual(body['targets'],[])
                        self.assertEqual(launch.call_count,1)
                        self.assertNotIn('private',json.dumps(body))
                finally:
                    server.shutdown(); thread.join(timeout=2)
                    fixture.close()

    def test_http_inspection_uncertainty_latches_unavailable(self):
        self.check_http_uncertainty('inspect')

    def test_http_termination_uncertainty_latches_unavailable(self):
        self.check_http_uncertainty('terminate')

    def test_http_scratch_cleanup_uncertainty_latches_unavailable(self):
        self.check_http_uncertainty('scratch')
