"""Metadata-only closure of imported original research Python modules."""
import ast
from pathlib import Path
from .contract import need
from .worker_artifact import read_owned
ROOT=Path(__file__).resolve().parents[3]
MODULE_ROOTS=('assessment-consumer-app','assessment-mobile-admission','assessment-admission','assessment-desktop-journey',
    'assessment-reference-assets','assessment-recording-access','assessment-review-service','assessment-workbench','audio-head')
# All originals remain in place; do not import their model/runtime modules here.
def research_dependencies():
    roots=[ROOT/'research'/name for name in MODULE_ROOTS];found={};pending=['consumer_app.server','consumer_app.catalog','consumer_app.feedback']
    def resolve(name):
        if not name or any(not part.isidentifier() for part in name.split('.')):return None
        candidates=[]
        for root in roots:
            target=root.joinpath(*name.split('.'))
            for file in (target.with_suffix('.py'),target/'__init__.py'):
                if file.is_file():candidates.append(file)
        need(len(candidates)<=1,'ambiguous_dependency')
        return candidates[0] if candidates else None
    while pending:
        name=pending.pop()
        if name in found:continue
        path=resolve(name)
        if path is None:continue # stdlib/installed native dependencies retain their existing frozen guards.
        found[name]=path
        if '.' in name:pending.append(name.rsplit('.',1)[0])
        text=read_owned(path,1048576).decode();tree=ast.parse(text,filename=str(path))
        package=name if path.name=='__init__.py' else name.rpartition('.')[0]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):pending.extend(alias.name for alias in node.names)
            elif isinstance(node,ast.ImportFrom):
                if node.level:
                    parts=package.split('.') if package else []
                    need(node.level<=len(parts),'invalid_relative_dependency')
                    prefix='.'.join(parts[:len(parts)-node.level+1]);target='.'.join(part for part in (prefix,node.module) if part)
                else:target=node.module or ''
                if target:pending.append(target)
                for alias in node.names:
                    if alias.name!='*' and target:pending.append(target+'.'+alias.name)
    return tuple(sorted(str(path.relative_to(ROOT)) for path in found.values()))
