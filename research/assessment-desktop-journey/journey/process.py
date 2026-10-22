"""Bounded trusted-worker tree cleanup; no adversarial containment claim."""
import os
import select
import signal
import subprocess
import sys
import time


class CleanupUnconfirmed(ValueError):
    pass


def process_table():
    try:
        response=subprocess.run(['/bin/ps','-axo','pid=,ppid=,stat=,lstart='],stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=0.4,check=True)
        if len(response.stdout)>2*1024*1024:raise CleanupUnconfirmed('cleanup_unconfirmed')
        records={}
        for line in response.stdout.decode('ascii').splitlines():
            parts=line.split(None,3)
            if len(parts)!=4:raise CleanupUnconfirmed('cleanup_unconfirmed')
            pid,parent,state,started=parts
            records[int(pid)]={'pid':int(pid),'ppid':int(parent),'state':state,'started':started}
        return records
    except (OSError,ValueError,subprocess.SubprocessError):
        raise CleanupUnconfirmed('cleanup_unconfirmed') from None


def _same(current,record):
    return bool(current and current['pid']==record['pid'] and current['started']==record['started'])


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
                if len(tracked)>=128:raise CleanupUnconfirmed('cleanup_unconfirmed')
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


def _cleanup(root_pid,tracked):
    deadline=time.monotonic()+2
    root=tracked.get(root_pid)
    if root is None:raise CleanupUnconfirmed('cleanup_unconfirmed')
    table=process_table();_signal(root,signal.SIGSTOP,table,tracked)
    stable=None
    while time.monotonic()<deadline:
        table=process_table();_track(table,tracked,root_pid)
        for record in list(tracked.values()):
            if time.monotonic()>=deadline:raise CleanupUnconfirmed('cleanup_unconfirmed')
            _signal(record,signal.SIGSTOP,table,tracked)
        identity={(pid,record['started']) for pid,record in tracked.items()}
        stopped=all(not _owned(table.get(pid),record,table,tracked) or table[pid]['state'].startswith(('T','Z')) for pid,record in tracked.items())
        if identity==stable and stopped:break
        stable=identity;time.sleep(0.02)
    else:raise CleanupUnconfirmed('cleanup_unconfirmed')
    terminated=0
    for record in sorted(tracked.values(),key=lambda r:_depth(r,tracked),reverse=True):
        if time.monotonic()>=deadline:raise CleanupUnconfirmed('cleanup_unconfirmed')
        table=process_table()
        if _signal(record,signal.SIGKILL,table,tracked) and record['pid']!=root_pid:terminated+=1
    while time.monotonic()<deadline:
        table=process_table()
        if all(not _owned(table.get(pid),record,table,tracked) or table[pid]['state'].startswith('Z') for pid,record in tracked.items()):
            return terminated
        time.sleep(0.02)
    raise CleanupUnconfirmed('cleanup_unconfirmed')


def supervise(command,raw,*,cwd,env,timeout_seconds,cancellation_event=None):
    started=time.monotonic()
    process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,start_new_session=True)
    os.set_blocking(process.stdin.fileno(),False)
    remaining=memoryview(raw);input_open=True;tracked={};timed_out=False;cancelled=False;confirmed=True;terminated=0;usage=None
    try:
        while True:
            table=process_table()
            if process.pid not in tracked:
                root=table.get(process.pid)
                if root is None:raise CleanupUnconfirmed('cleanup_unconfirmed')
                tracked[process.pid]=dict(root)
            _track(table,tracked,process.pid)
            root=table.get(process.pid)
            if not _same(root,tracked[process.pid]):raise CleanupUnconfirmed('cleanup_unconfirmed')
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
        terminated=_cleanup(process.pid,tracked)
    except (CleanupUnconfirmed,OSError,ValueError):
        confirmed=False
    finally:
        if input_open:process.stdin.close()
        # The unreaped direct child PID cannot be reused. Never broad group-kill.
        try:os.kill(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        _,status,usage=os.wait4(process.pid,0);process.returncode=os.waitstatus_to_exitcode(status)
    return {'elapsedSeconds':time.monotonic()-started,'peakRssKiB':usage.ru_maxrss/1024 if sys.platform=='darwin' else usage.ru_maxrss,
            'workerExitCode':process.returncode,'timedOut':timed_out,'acousticCalls':1,
            'cancelled':cancelled,'cleanupConfirmed':confirmed,'descendantsTerminated':terminated,'tracked':list(tracked.values())}
