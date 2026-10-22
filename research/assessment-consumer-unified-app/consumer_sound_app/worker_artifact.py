"""Explicit frozen external artifact; no downloader, fallback or acoustic import."""
from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import stat
from . import contract as c
ROOT=Path(__file__).resolve().parents[3]
REVIEWED_SOURCE_SHA='e392c577e289dcb944551bc95c2ea1ad05a39d420f18b5a6eb3a08d668e7ba04'
REVIEWED_RECEIPT_SHA='0c1762b9b6cab1499cb541663601bd261e03afba33e2e3453a6af35aebc50ca3'

def read_owned(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        c.need(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1 and 0<=before.st_size<=limit,'unsafe_source')
        raw=os.read(fd,limit+1);after=os.fstat(fd);live=path.lstat()
        identity=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
        c.need(len(raw)==before.st_size and identity(before)==identity(after) and identity(before)==identity(live),'source_changed')
        return raw
    finally:os.close(fd)

@dataclass(frozen=True)
class WorkerArtifact:
    directory:Path
    source_sha256:str
    receipt_sha256:str
    def __post_init__(self):
        c.need(type(self.directory) is Path or isinstance(self.directory,Path),'invalid_artifact_directory')
        c.need(c.hex64(self.source_sha256) and c.hex64(self.receipt_sha256) and self.source_sha256==REVIEWED_SOURCE_SHA and self.receipt_sha256==REVIEWED_RECEIPT_SHA,'unreviewed_worker')
        directory=self.directory
        c.need(directory.is_absolute() and directory==directory.resolve(),'unsafe_artifact_directory')
        info=directory.lstat();c.need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid(),'unsafe_artifact_directory')
        # Frozen supervisor/source map derive the repository root from this existing artifact layout.
        c.need(len(directory.parents)>=3 and directory.parents[2]==ROOT,'unsupported_artifact_layout')
    @classmethod
    def from_inputs(cls,inputs):
        c.need(c.exact(inputs,('artifactDirectory','sourceSha256','receiptSha256')),'invalid_artifact_configuration')
        path=inputs['artifactDirectory'];c.need(type(path) is str and 0<len(path)<=4096 and '\x00' not in path,'invalid_artifact_directory')
        return cls(Path(path),inputs['sourceSha256'],inputs['receiptSha256'])
    def verify(self):
        raw=read_owned(self.directory/'RECEIPT.json',65536);c.need(c.sha(raw)==self.receipt_sha256,'worker_receipt_changed')
        receipt=c.strict_json(raw);c.need(receipt['sourceSnapshotSha256']==self.source_sha256,'worker_source_changed')
        source=read_owned(self.directory/'supervisor.py',65536)
        c.need(c.sha(source)==receipt['files']['supervisor.py']['sha256'],'worker_source_changed')
        pins=read_owned(self.directory/'source-pins.json',65536);c.need(c.sha(pins)==self.source_sha256,'worker_source_changed')
        inventory=c.strict_json(pins)
        c.need(c.exact(inventory,('schemaVersion','files')) and type(inventory['schemaVersion']) is int and inventory['schemaVersion']==1 and type(inventory['files']) is list,'invalid_worker_inventory')
        entries=inventory['files']
        c.need(all(c.exact(row,('path','bytes','sha256')) and type(row['path']) is str and not Path(row['path']).is_absolute() and '..' not in Path(row['path']).parts for row in entries),'invalid_worker_inventory')
        matches=[row for row in entries if Path(row['path']).name=='supervisor.py' and row['sha256']==receipt['files']['supervisor.py']['sha256']]
        c.need(len(matches)==1,'invalid_worker_inventory')
        # HERE drives worker.ts and its sibling imports: bind it to the frozen source map, not merely root depth.
        pinned_parent=(ROOT/matches[0]['path']).parent
        c.need(pinned_parent==self.directory,'unsupported_artifact_relocation')
        worker_matches=[row for row in entries if ROOT/row['path']==pinned_parent/'worker.ts']
        c.need(len(worker_matches)==1 and c.hex64(worker_matches[0]['sha256']),'invalid_worker_inventory')
        driver=read_owned(self.directory/'worker.ts',65536)
        c.need(type(worker_matches[0]['bytes']) is int and len(driver)==worker_matches[0]['bytes'] and c.sha(driver)==worker_matches[0]['sha256'],'worker_source_changed')
        return receipt
    def load_api(self):
        self.verify()
        spec=importlib.util.spec_from_file_location('verified_local_sound_worker',self.directory/'supervisor.py')
        module=importlib.util.module_from_spec(spec)
        # Execute the verified source bytes, never an unbound timestamp-based .pyc.
        receipt=self.verify();source=read_owned(self.directory/'supervisor.py',65536)
        c.need(c.sha(source)==receipt['files']['supervisor.py']['sha256'],'worker_source_changed')
        exec(compile(source,str(self.directory/'supervisor.py'),'exec'),module.__dict__)
        c.need(module.ROOT==ROOT and module.HERE==self.directory,'unsupported_artifact_layout')
        module.snapshot(self.source_sha256);self.verify()
        return module
    def observer(self,worker,runtime_dir,cache_dir,*,node='node'):
        self.verify();worker.snapshot(self.source_sha256)
        return worker.ByteContrastObserver(runtime_dir,cache_dir,self.source_sha256,node=node,timeout_seconds=60)
