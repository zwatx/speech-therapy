import os,sys,time,unittest

class ProcessTests(unittest.TestCase):
    def test_timeout_includes_nonreading_stdin_and_reaps_the_worker(self):
        from admission.process import supervise
        start=time.monotonic()
        result=supervise([sys.executable,'-c','import time; time.sleep(30)'],b'x'*132096,
                         cwd=os.getcwd(),env=dict(os.environ),timeout_seconds=0.03)
        self.assertTrue(result['timedOut'])
        self.assertLess(time.monotonic()-start,2)
        self.assertLess(result['workerExitCode'],0)
        self.assertGreaterEqual(result['peakRssKiB'],0)

    def test_failed_worker_exit_has_terminal_resource_metadata_without_retry(self):
        from admission.process import supervise
        result=supervise([sys.executable,'-c','raise SystemExit(3)'],b'',cwd=os.getcwd(),env=dict(os.environ),timeout_seconds=2)
        self.assertFalse(result['timedOut'])
        self.assertEqual(result['workerExitCode'],3)
        self.assertEqual(result['acousticCalls'],1)
