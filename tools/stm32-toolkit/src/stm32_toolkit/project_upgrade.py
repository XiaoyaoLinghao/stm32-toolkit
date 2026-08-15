"""Explicit v1-to-v2 and v2-to-v3 project upgrade transactions."""
from __future__ import annotations
import json, os, re, stat
from collections.abc import Mapping as MappingABC
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Iterator, Mapping, cast
from uuid import uuid4
from stm32_toolkit import __version__
from stm32_toolkit.evidence.gc import _close_windows_handle, _file_identity_fields, _open_windows_file, _stable_parent_guard, _windows_file_information
from stm32_toolkit.evidence.model import canonical_json_bytes
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

@dataclass
class _PreparedUpgrade:
    plan:UpgradePlan; signature:tuple[object,...]; consumed:bool=False
_PREPARED:dict[str,_PreparedUpgrade]={}
_LEDGER_A=".stm32-project-mutation-ledger"; _LEDGER_B=".stm32-project-mutation-ledger-alt"

def _identity(path:Path)->dict[str,object]:
    info=path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400: raise OSError("unsafe identity")
    if stat.S_ISDIR(info.st_mode):
        return {"device":str(info.st_dev),"inode":str(info.st_ino)}
    return _file_identity_fields(path,info)

def _ledger(root:Path)->EvidenceStore:
    return EvidenceStore(root.parent/(_LEDGER_B if root.name.casefold()==_LEDGER_A.casefold() else _LEDGER_A))

@contextmanager
def project_mutation_lock(project_root:Path)->Iterator[None]:
    """Serialize all supported publishers for a canonical project pathname."""
    root=canonical_project_root(project_root); before=EvidenceStore._validate_existing_path(root.parent)
    if os.name == "nt":
        with _stable_parent_guard(root.parent,before):
            with _ledger(root)._mutation_lock(): yield
    else:  # pragma: no cover - exercised by the Linux acceptance owner
        with _ledger(root)._mutation_lock():
            current=EvidenceStore._validate_existing_path(root.parent)
            if (current.st_dev,current.st_ino)!=(before.st_dev,before.st_ino):raise OSError("project parent identity changed")
            yield

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
    plan=UpgradePlan(manifest,source,old,new,proposed,candidate,diff,pd,ad,ri,mi); _PREPARED[ad]=_PreparedUpgrade(plan,_signature(plan)); return plan

def apply_project_upgrade(plan:UpgradePlan,authorized:object,expected_plan_digest:object)->OperationResult[Mapping[str,object]]:
    """Consume and apply one explicit v1-to-v2 MODIFY action."""
    return _apply(plan,authorized,expected_plan_digest,1,2)

def apply_project_v2_to_v3_upgrade(plan:UpgradePlan,authorized:object,expected_plan_digest:object)->OperationResult[Mapping[str,object]]:
    """Consume and apply one explicit v2-to-v3 MODIFY action."""
    return _apply(plan,authorized,expected_plan_digest,2,3)

def _apply(plan:UpgradePlan,authorized:object,expected:object,old:int,new:int)->OperationResult[Mapping[str,object]]:
    if not isinstance(plan,UpgradePlan): return _invalid("plan","type")
    reg=_PREPARED.get(plan.action_digest)
    path=plan.manifest_path
    if reg is None:
        if not _canonical_manifest(path):return _invalid("manifestPath","canonicalProjectManifest")
        return _consumed(plan) if _is_consumed(path.parent,plan.action_digest) else _invalid("plan","registeredPreparedAction")
    exact=reg.plan is plan
    try:
        prepared_root=reg.plan.manifest_path.parent
        with project_mutation_lock(prepared_root):
            if reg.consumed:return _consumed(plan)
            reg.consumed=True
            if not _consume(prepared_root,reg.plan): return _consumed(plan)
            if reg.signature!=_signature(plan): return _invalid("plan","registeredPreparedAction")
            if not exact: return _invalid("plan","registeredPreparedAction")
            if not _canonical_manifest(path): return _invalid("manifestPath","canonicalProjectManifest")
            if type(plan.from_version) is not int or type(plan.to_version) is not int or (plan.from_version,plan.to_version)!=(old,new): return _versions(plan)
            if not isinstance(authorized,str) or authorized!=plan.action_digest: return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_AUTHORIZATION_REQUIRED","Exact project upgrade authorization is required",{"field":"authorized","rule":"exactActionDigest"})
            if not isinstance(expected,str) or expected!=plan.plan_digest: return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_PLAN_DIGEST_MISMATCH","Project upgrade plan digest does not match",{"expectedPlanDigest":plan.plan_digest,"observedPlanDigest":expected})
            if _identity(path.parent)!=_thaw(plan.root_identity): return _changed(path,plan.source_sha256,None)
            raw=_read_current(path); observed=None if raw is None else sha256(raw).hexdigest()
            if raw is None or observed!=plan.source_sha256 or _identity(path)!=_thaw(plan.manifest_identity): return _changed(path,plan.source_sha256,observed)
            payload=_parse(raw); _validate_packaged_schema(payload,old); validate_model_document(path.parent,payload,old)
            candidate=json.dumps(_build_v2(payload),indent=2,ensure_ascii=False)+"\n" if old==1 else _build_v3(raw)
            invalid=_proposed_validation_error(_parse(candidate.encode()),path.parent,new)
            if invalid:return _invalid("source",f"validSchemaVersion{old}")
            if candidate!=plan.candidate or _diff(raw.decode(),candidate,old,new)!=plan.diff: return _invalid("proposed","deterministicUpgrade")
            _publish(path,candidate,_thaw(plan.manifest_identity))
    except _StageError as error: return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_IO_ERROR","Project upgrade I/O error",{"path":str(path),"stage":error.stage})
    except (OSError,ProjectManifestError,ProjectUpgradeError): return _changed(path,plan.source_sha256,None)
    return OperationResult.success("project.upgrade",{"path":str(path),"fromVersion":old,"toVersion":new,"sourceSha256":plan.source_sha256,"resultSha256":sha256(plan.candidate.encode()).hexdigest(),"planDigest":plan.plan_digest,"actionDigest":plan.action_digest})

def _consume(root:Path,plan:UpgradePlan)->bool:
    ledger=_ledger(root); directory=ledger._managed_directory("actions"); target=directory/f"{plan.action_digest}.json"
    try: ledger._validate_existing_path(target,regular=True,single_link=True); return False
    except FileNotFoundError: return ledger._atomic_create_new(target,canonical_json_bytes({"action_digest":plan.action_digest,"plan_digest":plan.plan_digest,"root_identity":_thaw(plan.root_identity),"state":"consumed"}),phase="project-upgrade-authorization")
    except OSError: return False

def _is_consumed(root:Path,action_digest:str)->bool:
    if not isinstance(action_digest,str) or re.fullmatch(r"[0-9a-f]{64}",action_digest) is None:return False
    try:_ledger(root)._validate_existing_path(_ledger(root).root/"actions"/f"{action_digest}.json",regular=True,single_link=True);return True
    except (FileNotFoundError,OSError):return False

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

def _publish(path:Path,content:str,identity:object)->None:
    temp=path.parent/f".{path.name}.{uuid4().hex}.tmp"
    try:
        guard=_open_windows_file(path,delete=True) if os.name=="nt" else None
        try:
            if guard is not None:
                opened=_windows_file_information(guard)
                if str(opened["volume_serial"])!=identity.get("volume_serial") or str(opened["file_index"])!=identity.get("file_index"):raise _StageError("identity")
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"w",encoding="utf-8",newline="") as stream:stream.write(content);stream.flush();os.fsync(stream.fileno())
        finally:
            if guard is not None:_close_windows_handle(guard)
        if _identity(path)!=identity:raise _StageError("identity")
        _replace_identity_bound(path,temp)
    except _StageError:raise
    except OSError as error:raise _StageError("replace" if temp.exists() else "write") from error
    finally:
        try:temp.unlink()
        except OSError:pass

def _replace_identity_bound(path:Path,temp:Path)->None:
    """Publish with Windows ReplaceFile after the pinned identity validation."""
    if os.name!="nt":os.replace(temp,path);return
    import ctypes
    replace=ctypes.WinDLL("kernel32",use_last_error=True).ReplaceFileW
    replace.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p]
    replace.restype=ctypes.c_int
    if not replace(str(path),str(temp),None,0x00000001,None,None):raise ctypes.WinError(ctypes.get_last_error())

def _canonical_manifest(path:Path)->bool:
    if not isinstance(path,Path) or not path.is_absolute() or path.name!=_MANIFEST_NAME:return False
    try:return canonical_project_root(path.parent)==path.parent
    except OSError:return False
def _digest(value:Mapping[str,object])->str:return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def _signature(p:UpgradePlan)->tuple[object,...]:return(p.manifest_path,p.source_sha256,p.from_version,p.to_version,_thaw(p.proposed),p.candidate,p.diff,p.plan_digest,p.action_digest,_thaw(p.root_identity),_thaw(p.manifest_identity))
def _plan_signature(p:UpgradePlan)->tuple[object,...]:return _signature(p)
def _invalid(field:str,rule:str)->OperationResult[None]:return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_PLAN_INVALID","Project upgrade plan is invalid",{"field":field,"rule":rule})
def _versions(p:UpgradePlan)->OperationResult[None]:return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_PLAN_INVALID","Project upgrade plan is invalid",{"fromVersion":p.from_version,"toVersion":p.to_version})
def _consumed(p:UpgradePlan)->OperationResult[None]:return OperationResult.failure("project.upgrade","PROJECT_UPGRADE_AUTHORIZATION_CONSUMED","Project upgrade authorization was already consumed",{"actionDigest":p.action_digest})
def _changed(path:Path,expected:str,observed:str|None)->OperationResult[None]:return OperationResult.failure("project.upgrade","PROJECT_CHANGED_SINCE_PLAN","Project manifest changed since the upgrade plan was created",{"path":str(path),"expectedSha256":expected,"observedSha256":observed})
def _freeze(value:object)->object:
    if isinstance(value,MappingABC):return MappingProxyType({k:_freeze(v) for k,v in value.items()})
    if isinstance(value,(list,tuple)):return tuple(_freeze(v) for v in value)
    return value
def _thaw(value:object)->object:
    if isinstance(value,MappingABC):return{k:_thaw(v) for k,v in value.items()}
    if isinstance(value,tuple):return[_thaw(v) for v in value]
    return value
