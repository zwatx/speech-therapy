"""Bounded trusted-worker tree cleanup; no adversarial containment claim."""
import os
import select
import signal
import subprocess
import sys
import time


FAILURE_CODES = {'scan_timeout','scan_failed','scan_format_invalid','scan_limit','root_missing',
                 'root_identity_changed','tracking_limit','stop_timeout','kill_timeout','verify_timeout',
                 'signal_failed','stdin_failed','cleanup_unconfirmed'}


class CleanupUnconfirmed(ValueError):
    def __init__(self, code='cleanup_unconfirmed'):
        self.code = code if code in FAILURE_CODES else 'cleanup_unconfirmed'
        super().__init__(self.code)


def process_table(timeout_seconds=0.4):
    try:
        response=subprocess.run(['/bin/ps','-axo','pid=,ppid=,stat=,lstart='],stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout_seconds,check=True)
        if len(response.stdout)>2*1024*1024:raise CleanupUnconfirmed('scan_limit')
        records={}
        for line in response.stdout.decode('ascii').splitlines():
            parts=line.split(None,3)
            if len(parts)!=4:raise CleanupUnconfirmed('scan_format_invalid')
            pid,parent,state,started=parts
            records[int(pid)]={'pid':int(pid),'ppid':int(parent),'state':state,'started':started.strip()}
        return records
    except CleanupUnconfirmed:
        raise
    except subprocess.TimeoutExpired:
        raise CleanupUnconfirmed('scan_timeout') from None
    except (OSError,subprocess.SubprocessError):
        raise CleanupUnconfirmed('scan_failed') from None
    except ValueError:
        raise CleanupUnconfirmed('scan_format_invalid') from None


def _scan(deadline, metrics):
    """One transient retry within the existing budget; never reset ownership."""
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:raise CleanupUnconfirmed('scan_timeout')
        began = time.monotonic()
        try:
            table = process_table(timeout_seconds=min(0.4, remaining))
            metrics['_lastTable'] = table
            return table
        except CleanupUnconfirmed as error:
            if (attempt or error.code not in ('scan_timeout','scan_failed')
                    or time.monotonic() + 0.02 >= deadline):
                raise
            metrics['scanRetries'] += 1
            time.sleep(0.02)
        finally:
            elapsed = time.monotonic() - began
            metrics['scanCount'] += 1
            metrics['scanElapsedSeconds'] += elapsed
            metrics['scanMaximumSeconds'] = max(metrics['scanMaximumSeconds'], elapsed)


def _same(current,record):
    return bool(current and current['pid']==record['pid'] and current['started'].strip()==record['started'].strip())


def _track(table,tracked,root_pid):
    # Continuous snapshots retain evidence for children that later become orphans.
    found={root_pid}|set(tracked)
    changed=True
    while changed:
        changed=False
        for pid,record in table.items():
            if pid not in found and record['ppid'] in found:
                parent=table.get(record['ppid']);known=tracked.get(record['ppid'])
                if known and not _same(parent,known):continue
                if len(tracked)>=128:raise CleanupUnconfirmed('tracking_limit')
                tracked[pid]=dict(record);found.add(pid);changed=True


def _owned(current,record,table,tracked):
    if not _same(current,record):return False
    if current['ppid']==record['ppid']:return True
    parent=tracked.get(record['ppid'])
    old=table.get(record['ppid'])
    return bool(current['ppid']==1 and parent and (old is None or (_same(old,parent) and old['state'].startswith('Z'))))


def _depth(record,tracked):
    depth=0;seen=set();parent=record['ppid']
    while parent in tracked and parent not in seen:
        seen.add(parent);depth+=1;parent=tracked[parent]['ppid']
    return depth


def _signal(record,which,table,tracked):
    current=table.get(record['pid'])
    if not _owned(current,record,table,tracked) or current['state'].startswith('Z'):return False
    try:os.kill(record['pid'],which);return True
    except ProcessLookupError:return False


def _cleanup(root_pid,tracked,metrics):
    deadline=time.monotonic()+2
    root=tracked.get(root_pid)
    if root is None:raise CleanupUnconfirmed('root_missing')
    def scan():
        table=_scan(deadline,metrics)
        # The direct Popen child stays unreaped until cleanup finishes. A
        # missing/changed root cannot be interpreted as confirmed cleanup.
        current=table.get(root_pid)
        if current is None:raise CleanupUnconfirmed('root_missing')
        if not _same(current,root):raise CleanupUnconfirmed('root_identity_changed')
        return table
    table=scan();_signal(root,signal.SIGSTOP,table,tracked)
    stable=None
    while time.monotonic()<deadline:
        table=scan();_track(table,tracked,root_pid)
        for record in list(tracked.values()):
            if time.monotonic()>=deadline:raise CleanupUnconfirmed('stop_timeout')
            _signal(record,signal.SIGSTOP,table,tracked)
        identity={(pid,record['started']) for pid,record in tracked.items()}
        stopped=all(not _owned(table.get(pid),record,table,tracked) or table[pid]['state'].startswith(('T','Z')) for pid,record in tracked.items())
        if identity==stable and stopped:break
        stable=identity;time.sleep(0.02)
    else:raise CleanupUnconfirmed('stop_timeout')
    terminated=0
    for record in sorted(tracked.values(),key=lambda r:_depth(r,tracked),reverse=True):
        if time.monotonic()>=deadline:raise CleanupUnconfirmed('kill_timeout')
        table=scan()
        if _signal(record,signal.SIGKILL,table,tracked) and record['pid']!=root_pid:terminated+=1
    while time.monotonic()<deadline:
        table=scan()
        if all(not _owned(table.get(pid),record,table,tracked) or table[pid]['state'].startswith('Z') for pid,record in tracked.items()):
            return terminated
        time.sleep(0.02)
    raise CleanupUnconfirmed('verify_timeout')


def supervise(command,raw,*,cwd,env,timeout_seconds,cancellation_event=None):
    started=time.monotonic()
    process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,start_new_session=True)
    os.set_blocking(process.stdin.fileno(),False)
    remaining=memoryview(raw);input_open=True;tracked={};timed_out=False;cancelled=False;confirmed=True;terminated=0;usage=None
    metrics={'scanCount':0,'scanElapsedSeconds':0.0,'scanMaximumSeconds':0.0,'scanRetries':0}
    failure_phase = None; failure_code = None; phase = 'monitor'
    try:
        while True:
            if time.monotonic()-started>=timeout_seconds:timed_out=True;break
            table=_scan(started+timeout_seconds,metrics)
            if process.pid not in tracked:
                root=table.get(process.pid)
                if root is None:raise CleanupUnconfirmed('root_missing')
                tracked[process.pid]=dict(root)
            _track(table,tracked,process.pid)
            root=table.get(process.pid)
            if not _same(root,tracked[process.pid]):raise CleanupUnconfirmed('root_identity_changed')
            if root['state'].startswith('Z'):break
            if cancellation_event is not None and cancellation_event.is_set():cancelled=True;break
            if time.monotonic()-started>=timeout_seconds:timed_out=True;break
            if input_open:
                try:
                    if select.select([], [process.stdin], [], 0.02)[1]:
                        count=os.write(process.stdin.fileno(),remaining);remaining=remaining[count:]
                        if not remaining:process.stdin.close();input_open=False
                except BrokenPipeError:process.stdin.close();input_open=False
            else:time.sleep(0.02)
        phase = 'cleanup'
        terminated=_cleanup(process.pid,tracked,metrics)
    except (CleanupUnconfirmed,OSError,ValueError) as error:
        if phase == 'monitor' and time.monotonic() >= started+timeout_seconds:
            timed_out=True
        failure_phase = phase
        failure_code = error.code if isinstance(error,CleanupUnconfirmed) else 'signal_failed' if phase == 'cleanup' else 'stdin_failed'
        confirmed=False
        # A monitor failure does not waive cleanup of already identified workers.
        if phase == 'monitor' and process.pid in tracked:
            try:
                terminated=_cleanup(process.pid,tracked,metrics)
                confirmed=True
            except (CleanupUnconfirmed,OSError,ValueError):
                pass
    finally:
        if input_open:process.stdin.close()
        # The unreaped direct child PID cannot be reused. Never broad group-kill.
        try:os.kill(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        _,status,usage=os.wait4(process.pid,0);process.returncode=os.waitstatus_to_exitcode(status)
    last_table=metrics.pop('_lastTable',{})
    last_observed=[dict(last_table[pid]) for pid in sorted(tracked) if pid in last_table]
    return {'elapsedSeconds':time.monotonic()-started,'peakRssKiB':usage.ru_maxrss/1024 if sys.platform=='darwin' else usage.ru_maxrss,
            'workerExitCode':process.returncode,'timedOut':timed_out,'acousticCalls':1,
            'cancelled':cancelled,'cleanupConfirmed':confirmed,'descendantsTerminated':terminated,'tracked':list(tracked.values()),
            'cleanupFailurePhase':failure_phase,'cleanupFailureCode':failure_code,
            'supervisionFailed':failure_phase is not None,'lastObserved':last_observed,**metrics}
