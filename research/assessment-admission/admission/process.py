"""Bounded process supervision; includes stdin, kill/reap and real resource use."""
import os,select,signal,subprocess,sys,time

def supervise(command,raw,*,cwd,env,timeout_seconds):
    started=time.monotonic()
    process=subprocess.Popen(command,cwd=cwd,env=env,
                              stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    os.set_blocking(process.stdin.fileno(),False)
    remaining=memoryview(raw);input_open=True
    timeout=False;usage=None
    try:
        while True:
            pid,status,usage=os.wait4(process.pid,os.WNOHANG)
            if pid:
                process.returncode=os.waitstatus_to_exitcode(status);break
            if time.monotonic()-started>=timeout_seconds:
                timeout=True;os.killpg(process.pid,signal.SIGKILL)
                _,status,usage=os.wait4(process.pid,0)
                process.returncode=os.waitstatus_to_exitcode(status);break
            if input_open:
                try:
                    if select.select([], [process.stdin], [], 0.02)[1]:
                        count=os.write(process.stdin.fileno(),remaining)
                        remaining=remaining[count:]
                        if not remaining:
                            process.stdin.close();input_open=False
                except BrokenPipeError:
                    process.stdin.close();input_open=False
            else:time.sleep(0.02)
    finally:
        if input_open:process.stdin.close()
        if process.returncode is None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            _,status,usage=os.wait4(process.pid,0);process.returncode=os.waitstatus_to_exitcode(status)
    runtime={'elapsedSeconds':time.monotonic()-started,'peakRssKiB':usage.ru_maxrss/1024 if sys.platform=='darwin' else usage.ru_maxrss,
             'workerExitCode':process.returncode,'timedOut':timeout,'acousticCalls':1}
    return runtime
