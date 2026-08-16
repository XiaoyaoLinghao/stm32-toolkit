"""Explicit v1-to-v2 and v2-to-v3 project upgrade transactions."""
from __future__ import annotations
import ctypes, errno, json, os, re, stat, threading
from collections.abc import Mapping as MappingABC
from contextlib import ExitStack, contextmanager, nullcontext
from copy import deepcopy
from dataclasses import dataclass, field
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Iterator, Mapping, cast
from uuid import uuid4
from stm32_toolkit import __version__
from stm32_toolkit.evidence.gc import _file_identity_fields, _stable_parent_guard
from stm32_toolkit.evidence.model import EvidenceValidationError, canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.identity import canonical_project_root
from stm32_toolkit.project_model import SOURCE_MAPPING, ProjectManifestError, _MANIFEST_NAME, _canonical_root, _packaged_first_schema_error, _require_manifest_object, _require_schema_version, _validate_packaged_schema, validate_model_document
from stm32_toolkit.result import OperationResult

class ProjectUpgradeError(Exception):
    def __init__(self, code:str, message:str, details:Mapping[str,object])->None:
        super().__init__(message); self.code=code; self.message=message; self.details=dict(details)

@dataclass(frozen=True)
class UpgradePlan:
    manifest_path:Path; source_sha256:str; from_version:int; to_version:int
    proposed:Mapping[str,object]; candidate:str; diff:str; plan_digest:str; action_digest:str
    root_identity:Mapping[str,object]=field(default_factory=dict); manifest_identity:Mapping[str,object]=field(default_factory=dict)
    def __post_init__(self)->None:
        for name in ("proposed","root_identity","manifest_identity"):
            object.__setattr__(self,name,cast(Mapping[str,object],_freeze(getattr(self,name))))

class _StageError(Exception):
    def __init__(self,stage:str)->None: super().__init__(stage); self.stage=stage

class _SourceChanged(Exception):
    def __init__(self,observed:str|None)->None:super().__init__(observed);self.observed=observed

@dataclass
class _PreparedUpgrade:
    plan:UpgradePlan; signature:tuple[object,...]; original_id:int; consumed:bool=False
    consume_lock:threading.Lock=field(default_factory=threading.Lock)
_PREPARED:dict[str,_PreparedUpgrade]={}
_LEDGER_A=".stm32-project-mutation-ledger"; _LEDGER_B=".stm32-project-mutation-ledger-alt"

def _identity(path:Path)->dict[str,object]:
    info=path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400: raise OSError("unsafe identity")
    if stat.S_ISDIR(info.st_mode):
        return {"device":str(info.st_dev),"inode":str(info.st_ino)}
    return _file_identity_fields(path,info)

def _ledgers(root:Path)->tuple[EvidenceStore,...]:
    root_path=os.path.normcase(str(root.absolute()))
    return tuple(EvidenceStore(root.parent/name) for name in (_LEDGER_A,_LEDGER_B) if os.path.normcase(str((root.parent/name).absolute()))!=root_path)

def _ledger(root:Path)->EvidenceStore:
    return _ledgers(root)[0]

@contextmanager
def project_mutation_lock(project_root:Path)->Iterator[EvidenceStore]:
    """Serialize all supported publishers for a canonical project pathname."""
    root=canonical_project_root(project_root); before=EvidenceStore._validate_existing_path(root.parent)
    guard=_stable_parent_guard(root.parent,before) if os.name=="nt" else nullcontext()
    with guard:
        acquired:list[EvidenceStore]=[]
        stack=ExitStack()
        try:
            for ledger in _ledgers(root):
                try:
                    stack.enter_context(ledger._mutation_lock())
                    acquired.append(ledger)
                except (OSError,EvidenceValidationError) as error:
                    if acquired:
                        raise EvidenceValidationError(
                            "project mutation ledger set is partially unavailable"
                        ) from error
                    continue
            if not acquired:raise EvidenceValidationError("project mutation ledgers are unavailable")
            current=EvidenceStore._validate_existing_path(root.parent)
            if (current.st_dev,current.st_ino)!=(before.st_dev,before.st_ino):raise EvidenceValidationError("project parent identity changed")
            yield acquired[0]
        finally:
            stack.close()

def plan_project_upgrade(project_root:Path)->UpgradePlan:
    """Prepare the historical explicit Schema v1-to-v2 route."""
    return _plan(project_root,1,2)

def plan_project_v2_to_v3_upgrade(project_root:Path)->UpgradePlan:
    """Prepare the independent Schema v2-to-v3 route."""
    return _plan(project_root,2,3)

def upgrade_project_v2_to_v3(project_root:Path)->UpgradePlan:
    return plan_project_v2_to_v3_upgrade(project_root)

def _plan(project_root:Path,old:int,new:int)->UpgradePlan:
    root=_canonical_root(project_root); manifest=root/_MANIFEST_NAME; raw=_read_manifest_bytes(manifest); payload=_parse(raw)
    version=_require_schema_version(payload)
    if version!=old:
        if version in (1,2,3): raise ProjectUpgradeError("PROJECT_UPGRADE_NOT_REQUIRED","Project is not on the route source version",{"schemaVersion":version,"route":f"v{old}-to-v{new}"})
        raise ProjectUpgradeError("PROJECT_SCHEMA_VERSION_UNSUPPORTED","Project schema version is not supported",{"schemaVersion":version,"supported":[1,2,3]})
    _validate_packaged_schema(payload,old); validate_model_document(root,payload,old)
    proposed=_build_v2(payload) if old==1 else _parse(_build_v3(raw).encode())
    candidate=json.dumps(proposed,indent=2,ensure_ascii=False)+"\n" if old==1 else _build_v3(raw)
    invalid=_proposed_validation_error(proposed,root,new)
    if invalid: raise ProjectUpgradeError("PROJECT_UPGRADE_PLAN_INVALID",f"Proposed project manifest is not valid schema version {new}",{"field":invalid[0],"rule":invalid[1]})
    source=sha256(raw).hexdigest(); diff=_diff(raw.decode(),candidate,old,new); ri=_identity(root); mi=_identity(manifest)
    bound={"manifestPath":str(manifest),"sourceSha256":source,"fromVersion":old,"toVersion":new,"candidate":candidate,"diff":diff,"rootIdentity":ri,"manifestIdentity":mi}
    pd=_digest(bound); ad=_digest({"operation":f"project.upgrade.v{old}-to-v{new}.apply","planDigest":pd,"sourceSha256":source})
    plan=UpgradePlan(manifest,source,old,new,proposed,candidate,diff,pd,ad,ri,mi)
    snapshot=UpgradePlan(manifest,source,old,new,proposed,candidate,diff,pd,ad,ri,mi)
    _PREPARED[ad]=_PreparedUpgrade(snapshot,_signature(snapshot),id(plan)); return plan

def apply_project_upgrade(plan:UpgradePlan,authorized:object,expected_plan_digest:object)->OperationResult[Mapping[str,object]]:
    """Consume and apply one explicit v1-to-v2 MODIFY action."""
    return _apply(plan,authorized,expected_plan_digest,1,2)

def apply_project_v2_to_v3_upgrade(plan:UpgradePlan,authorized:object,expected_plan_digest:object)->OperationResult[Mapping[str,object]]:
    """Consume and apply one explicit v2-to-v3 MODIFY action."""
    return _apply(plan,authorized,expected_plan_digest,2,3)

def _apply(plan:UpgradePlan,authorized:object,expected:object,old:int,new:int)->OperationResult[Mapping[str,object]]:
    if not isinstance(plan,UpgradePlan):
        return _invalid("plan","type")
    action=plan.action_digest
    if not isinstance(action,str) or re.fullmatch(r"[0-9a-f]{64}",action) is None:
        return _invalid("actionDigest","sha256")
    reg=_PREPARED.get(action)
    if reg is None:
        path=plan.manifest_path
        if not _canonical_manifest(path):
            return _invalid("manifestPath","canonicalProjectManifest")
        return _consumed_digest(action) if _is_consumed(path.parent,action) else _invalid("plan","registeredPreparedAction")
    exact=reg.original_id==id(plan)
    with reg.consume_lock:
        if reg.consumed:
            return _consumed_digest(action)
        reg.consumed=True
    path=reg.plan.manifest_path
    try:
        prepared_root=path.parent
        with project_mutation_lock(prepared_root) as ledger:
            consumed=_consume(prepared_root,reg.plan,ledger)
            if consumed is False:
                return _consumed_digest(action)
            try:signature_matches=reg.signature==_signature(plan)
            except (AttributeError,TypeError,ValueError,OverflowError):signature_matches=False
            if not signature_matches:
                return _invalid("plan","registeredPreparedAction")
            if not exact:
                return _invalid("plan","registeredPreparedAction")
            path=plan.manifest_path
            if not _canonical_manifest(path):
                return _invalid("manifestPath","canonicalProjectManifest")
            if type(plan.from_version) is not int or type(plan.to_version) is not int or (plan.from_version,plan.to_version)!=(old,new):
                return _versions(plan)
            if not isinstance(authorized,str) or authorized!=plan.action_digest:
                return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_AUTHORIZATION_REQUIRED","Exact project upgrade authorization is required",{"field":"authorized","rule":"exactActionDigest"})
            if not isinstance(expected,str) or expected!=plan.plan_digest:
                return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_PLAN_DIGEST_MISMATCH","Project upgrade plan digest does not match",{"expectedPlanDigest":plan.plan_digest if isinstance(plan.plan_digest,str) else None,"observedPlanDigest":expected if isinstance(expected,str) else None})
            if _identity(path.parent)!=_thaw(plan.root_identity):
                return _changed(path,plan.source_sha256,None)
            raw=_read_current(path); observed=None if raw is None else sha256(raw).hexdigest()
            if raw is None or observed!=plan.source_sha256 or _identity(path)!=_thaw(plan.manifest_identity):
                return _changed(path,plan.source_sha256,observed)
            payload=_parse(raw); _validate_packaged_schema(payload,old); validate_model_document(path.parent,payload,old)
            candidate=json.dumps(_build_v2(payload),indent=2,ensure_ascii=False)+"\n" if old==1 else _build_v3(raw)
            invalid=_proposed_validation_error(_parse(candidate.encode()),path.parent,new)
            if invalid:
                return _invalid("source",f"validSchemaVersion{old}")
            if candidate!=plan.candidate or _diff(raw.decode(),candidate,old,new)!=plan.diff:
                return _invalid("proposed","deterministicUpgrade")
            _publish(path,candidate,_thaw(plan.manifest_identity),plan.source_sha256)
    except _SourceChanged as error:return _changed(path,reg.plan.source_sha256,error.observed)
    except _StageError as error: return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_IO_ERROR","Project upgrade I/O error",{"path":str(path),"stage":error.stage})
    except (OSError,EvidenceValidationError,ProjectManifestError,ProjectUpgradeError): return _infra("authorizationLedger")
    return OperationResult.success("project.upgrade",{"path":str(path),"fromVersion":old,"toVersion":new,"sourceSha256":plan.source_sha256,"resultSha256":sha256(plan.candidate.encode()).hexdigest(),"planDigest":plan.plan_digest,"actionDigest":plan.action_digest})

def _consume(root:Path,plan:UpgradePlan,ledger:EvidenceStore)->bool:
    if _is_consumed(root,plan.action_digest):
        return False
    payload=canonical_json_bytes({"action_digest":plan.action_digest,"plan_digest":plan.plan_digest,"root_identity":_thaw(plan.root_identity),"state":"consumed"})
    stores=(ledger,)+tuple(item for item in _ledgers(root) if item.root!=ledger.root)
    last_error:Exception|None=None
    for store in stores:
        try:
            directory=store._managed_directory("actions");target=directory/f"{plan.action_digest}.json"
            return store._atomic_create_new(target,payload,phase="project-upgrade-authorization")
        except (OSError,EvidenceValidationError) as error:last_error=error
    raise EvidenceValidationError("project mutation authorization could not be persisted") from last_error

def _is_consumed(root:Path,action_digest:str)->bool:
    if not isinstance(action_digest,str) or re.fullmatch(r"[0-9a-f]{64}",action_digest) is None:
        return False
    for ledger in _ledgers(root):
        try:ledger._validate_existing_path(ledger.root/"actions"/f"{action_digest}.json",regular=True,single_link=True);return True
        except (FileNotFoundError,OSError,EvidenceValidationError):continue
    return False

def _build_v2(payload:dict)->dict:
    value=deepcopy(payload); value["schemaVersion"]=2; value["generatedBy"]={"tool":"stm32-toolkit","version":__version__}
    if isinstance(value.get("framework"),dict) and "version" not in value["framework"]: value["framework"]["version"]=None
    if isinstance(value.get("build"),dict): value["build"]["presets"]=[]
    origin=value.get("project",{}).get("origin","") if isinstance(value.get("project"),dict) else ""
    value["memory"]={"source":SOURCE_MAPPING.get(origin,"manual"),"regions":[]}; value["generation"]={"cubeMxIoc":None,"managedManifest":".stm32-toolkit/generated-files.json","generatedDirectories":[],"userDirectories":[]}; return value

def _build_v3(raw:bytes)->str:
    value,count=re.subn(r'("schemaVersion"\s*:\s*)2(?=\s*[,}])',r"\g<1>3",raw.decode(),count=1)
    if count!=1: raise ProjectUpgradeError("PROJECT_UPGRADE_PLAN_INVALID","Schema version could not be upgraded deterministically",{"field":"schemaVersion","rule":"deterministicUpgrade"})
    return value
_build_candidate = _build_v3

def _diff(source:str,candidate:str,old:int,new:int)->str:
    return "".join(unified_diff(source.splitlines(keepends=True),candidate.splitlines(keepends=True),fromfile=f"{_MANIFEST_NAME} (v{old})",tofile=f"{_MANIFEST_NAME} (v{new})"))

def _proposed_validation_error(proposed:Mapping[str,object],root:Path,version:int=3)->tuple[str,str]|None:
    first=_packaged_first_schema_error(proposed,version)
    if first:return first
    try: validate_model_document(root,cast(dict,proposed),version)
    except ProjectManifestError as error:return cast(str,error.details["field"]),cast(str,error.details["rule"])
    return None

def _read_manifest_bytes(path:Path)->bytes:
    try:return path.read_bytes()
    except OSError as error:raise ProjectManifestError("PROJECT_NOT_CONFIGURED","Project manifest is not available",{"path":_MANIFEST_NAME}) from error
def _read_current(path:Path)->bytes|None:
    try:return path.read_bytes()
    except OSError:return None
def _parse(raw:bytes)->dict:
    try:value=json.loads(raw.decode())
    except (UnicodeDecodeError,json.JSONDecodeError) as error:raise ProjectManifestError("PROJECT_JSON_INVALID","Project manifest is not valid JSON",{"path":"$"}) from error
    return _require_manifest_object(value)

def _publish(path:Path,content:str,identity:object,source_sha256:str)->None:
    temp=path.parent/f".{path.name}.{uuid4().hex}.tmp"
    try:
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="utf-8",newline="") as stream:stream.write(content);stream.flush();os.fsync(stream.fileno())
        if os.name=="nt":_exchange_windows(path,temp,identity,source_sha256)
        else:_exchange_posix(path,temp,identity,source_sha256)
        _fsync_directory(path.parent)
    except (_StageError,_SourceChanged):raise
    except OSError as error:raise _StageError("replace" if temp.exists() else "write") from error
    finally:
        try:temp.unlink()
        except OSError:pass

def _replace_identity_bound(path:Path,temp:Path,backup:Path)->None:
    """Atomically replace *path*, capturing its actual old target in *backup*."""
    replace=ctypes.WinDLL("kernel32",use_last_error=True).ReplaceFileW
    replace.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p]
    replace.restype=ctypes.c_int
    if not replace(str(path),str(temp),str(backup),0x00000001,None,None):raise ctypes.WinError(ctypes.get_last_error())

def _exchange_windows(path:Path,temp:Path,identity:object,source_sha256:str)->None:
    backup=path.parent/f".{path.name}.{uuid4().hex}.old"
    displaced=path.parent/f".{path.name}.{uuid4().hex}.new"
    try:
        _replace_identity_bound(path,temp,backup)
        captured=_read_current(backup); observed=None if captured is None else sha256(captured).hexdigest()
        matches=isinstance(identity,MappingABC) and observed==source_sha256
        try:matches=matches and _identity(backup)==dict(identity)
        except OSError:matches=False
        if matches:
            backup.unlink()
            return
        try:
            _replace_identity_bound(path,backup,displaced)
            restored=_read_current(path)
            if captured is None or restored!=captured:raise _StageError("restore")
            try:displaced.unlink()
            except OSError:pass
            _fsync_directory(path.parent)
        except (OSError,_StageError) as error:
            try:
                os.replace(backup,path)
                restored=_read_current(path)
                if captured is None or restored!=captured:
                    raise _StageError("restore")
                _fsync_directory(path.parent)
            except (OSError,_StageError) as fallback_error:
                raise _StageError("restore") from fallback_error
            raise _SourceChanged(observed) from error
        raise _SourceChanged(observed)
    finally:
        for item in (backup,displaced):
            try:item.unlink()
            except OSError:pass

def _exchange_posix(path:Path,temp:Path,identity:object,source_sha256:str)->None:
    if not _rename_exchange(path,temp):raise _StageError("exchangeUnavailable")
    captured=_read_current(temp); observed=None if captured is None else sha256(captured).hexdigest()
    matches=isinstance(identity,MappingABC) and observed==source_sha256
    try:matches=matches and _identity(temp)==dict(identity)
    except OSError:matches=False
    if matches:
        temp.unlink();return
    try:
        if not _rename_exchange(path,temp):raise _StageError("restore")
        restored=_read_current(path)
        if captured is None or restored!=captured:raise _StageError("restore")
        _fsync_directory(path.parent)
    except (OSError,_StageError) as error:raise _StageError("restore") from error
    raise _SourceChanged(observed)

def _rename_exchange(left:Path,right:Path)->bool:
    """Use Linux renameat2(RENAME_EXCHANGE); unsupported platforms fail closed."""
    if os.name!="posix":return False
    libc=ctypes.CDLL(None,use_errno=True)
    rename=getattr(libc,"renameat2",None)
    if rename is None:return False
    rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    rename.restype=ctypes.c_int
    if rename(-100,os.fsencode(left),-100,os.fsencode(right),2)==0:return True
    error=ctypes.get_errno()
    if error in (errno.ENOSYS,errno.EINVAL,errno.ENOTSUP):return False
    raise OSError(error,os.strerror(error))

def _fsync_directory(path:Path)->None:
    if os.name=="nt":return
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def _canonical_manifest(path:Path)->bool:
    if not isinstance(path,Path) or not path.is_absolute() or path.name!=_MANIFEST_NAME:return False
    try:return canonical_project_root(path.parent)==path.parent
    except OSError:return False
def _digest(value:Mapping[str,object])->str:return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def _signature(p:UpgradePlan)->tuple[object,...]:return(p.manifest_path,p.source_sha256,p.from_version,p.to_version,_thaw(p.proposed),p.candidate,p.diff,p.plan_digest,p.action_digest,_thaw(p.root_identity),_thaw(p.manifest_identity))
def _plan_signature(p:UpgradePlan)->tuple[object,...]:return _signature(p)
def _invalid(field:str,rule:str)->OperationResult[None]:return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_PLAN_INVALID","Project upgrade plan is invalid",{"field":field,"rule":rule})
def _versions(p:UpgradePlan)->OperationResult[None]:return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_PLAN_INVALID","Project upgrade plan is invalid",{"field":"versions","rule":"route"})
def _consumed(p:UpgradePlan)->OperationResult[None]:return _consumed_digest(p.action_digest if isinstance(p.action_digest,str) else "")
def _consumed_digest(action:str)->OperationResult[None]:return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_AUTHORIZATION_CONSUMED","Project upgrade authorization was already consumed",{"actionDigest":action})
def _infra(stage:str)->OperationResult[None]:return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_INFRA_ERROR","Project upgrade infrastructure is unavailable",{"stage":stage})
def _changed(path:Path,expected:str,observed:str|None)->OperationResult[None]:return OperationResult.failure("project.upgrade","PROJECT_CHANGED_SINCE_PLAN","Project manifest changed since the upgrade plan was created",{"path":str(path),"expectedSha256":expected,"observedSha256":observed})
def _freeze(value:object)->object:
    if isinstance(value,MappingABC):return MappingProxyType({k:_freeze(v) for k,v in value.items()})
    if isinstance(value,(list,tuple)):return tuple(_freeze(v) for v in value)
    return value
def _thaw(value:object)->object:
    if isinstance(value,MappingABC):return{k:_thaw(v) for k,v in value.items()}
    if isinstance(value,tuple):return[_thaw(v) for v in value]
    return value
