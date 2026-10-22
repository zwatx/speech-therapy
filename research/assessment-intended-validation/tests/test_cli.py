import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

class CliTests(unittest.TestCase):
    def test_actual_prepare_report_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp,0o700); root=Path(tmp).resolve()/'prepared'
            command=[sys.executable,'-m','intended_validation','prepare',str(root),'a'*64,'b'*64]
            first=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            self.assertEqual(json.loads(first.stdout)['collectedParticipants'],0)
            for name in ('protocol.json','observations.json','preparation-report.json'):
                self.assertEqual((root/name).stat().st_mode & 0o777,0o600)
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            command=[sys.executable,'-m','intended_validation','report',str(root/'protocol.json'),str(root/'observations.json'),str(root/'report.json')]
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
    def test_nonprivate_and_duplicate_json_fail_without_disclosing_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp,0o700); root=Path(tmp).resolve()/'prepared'
            command=[sys.executable,'-m','intended_validation','prepare',str(root),'a'*64,'b'*64]
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            raw=(root/'observations.json').read_bytes()
            (root/'observations.json').write_bytes(b'{"secret":"never-echo-this","secret":1}')
            command=[sys.executable,'-m','intended_validation','report',str(root/'protocol.json'),str(root/'observations.json'),str(root/'report.json')]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertNotIn('never-echo-this',result.stdout+result.stderr)
            (root/'observations.json').write_bytes(raw);os.chmod(root/'observations.json',0o644)
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)

    def test_unknown_arguments_are_sanitized(self):
        result=subprocess.run([sys.executable,'-m','intended_validation','never-echo-this'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertNotIn('never-echo-this',result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['error'],'invalid_command')

if __name__=='__main__':unittest.main()
