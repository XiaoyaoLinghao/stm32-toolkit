import argparse,hashlib,json,os,re,secrets,stat
from pathlib import Path,PurePosixPath
parser=argparse.ArgumentParser();parser.add_argument("--support",type=Path,required=True);parser.add_argument("--package",type=Path);parser.add_argument("--package-lock",type=Path);args=parser.parse_args();root=args.support.absolute()
doc=json.loads((root/"support-manifest.json").read_text("utf-8"));rows=doc.get("files")
if doc.get("schemaVersion")!=1 or not isinstance(rows,list): raise SystemExit("support manifest is invalid")
seen=set()
def relative_name(value: object,label: str) -> PurePosixPath:
 if not isinstance(value,str): raise SystemExit(f"{label} is not a string")
 pure=PurePosixPath(value)
 if pure.is_absolute() or not pure.parts or ".." in pure.parts or "." in pure.parts or pure.as_posix()!=value: raise SystemExit(f"{label} is not canonical relative POSIX")
 return pure
def canonical(path: Path,label: str,kind: str) -> Path:
 path=path.absolute();resolved=path.resolve(strict=True)
 try: resolved.relative_to(root.resolve(strict=True)) if path!=root else None
 except ValueError: raise SystemExit(f"{label} escapes support root")
 current=Path(path.anchor)
 for part in path.parts[1:]:
  names={entry.name for entry in os.scandir(current)}
  if part not in names: raise SystemExit(f"{label} is not case-exact")
  current/=part;metadata=os.lstat(current)
  if stat.S_ISLNK(metadata.st_mode) or getattr(metadata,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400): raise SystemExit(f"{label} contains a redirect")
 if resolved!=path or (kind=="file" and not path.is_file()) or (kind=="dir" and not path.is_dir()): raise SystemExit(f"{label} is not canonical {kind}")
 return path
root=canonical(root,"SupportRoot","dir")
manifest=canonical(root/"support-manifest.json","support-manifest.json","file")
try: fd=os.open(manifest,os.O_WRONLY|os.O_APPEND)
except PermissionError: pass
else:
 os.close(fd);raise SystemExit("support manifest is writable")
probe=root/(".stm32tk-readonly-probe-"+secrets.token_hex(32))
if os.path.lexists(probe): raise SystemExit("readonly probe path already exists")
temporary=getattr(os,"O_TEMPORARY",None)
if temporary is None: raise SystemExit("O_TEMPORARY is unavailable; cannot prove support root is readonly")
try: fd=os.open(probe,os.O_CREAT|os.O_EXCL|os.O_WRONLY|temporary,0o600)
except PermissionError: pass
else:
 os.close(fd)
 try: probe.unlink()
 except OSError: pass
 raise SystemExit("support root is writable")
if os.path.lexists(probe): raise SystemExit("readonly probe left residue")
def member(value: object,label: str,kind: str) -> Path:
 pure=relative_name(value,label);return canonical(root.joinpath(*pure.parts),label,kind)
for row in rows:
 name=row["path"];pure=relative_name(name,"files.path")
 if name in seen: raise SystemExit("support member is duplicate")
 seen.add(name);path=member(name,"files.path","file")
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 if path.stat().st_size!=row["bytes"] or digest!=row["sha256"]: raise SystemExit("support member hash differs")
actual={path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}-{"support-manifest.json"}
if actual!=seen: raise SystemExit("support inventory is not exhaustive")
artifacts_root=member(doc.get("artifacts"),"artifacts","dir")
artifacts=doc.get("pythonArtifacts",{});required={"setuptools","wheel","build","pytest","pytest-cov","coverage","aiohttp","jsonschema","mcp","pyelftools","jinja2","pyocd"}
if set(artifacts)!=required or int(artifacts["setuptools"]["version"].split(".")[0])<68: raise SystemExit("Python artifact set is invalid")
for name,artifact in artifacts.items():
 path=member(artifact.get("path"),f"pythonArtifacts.{name}.path","file")
 try:path.relative_to(artifacts_root)
 except ValueError:raise SystemExit(f"python artifact escapes artifacts: {name}")
 if artifact["path"] not in seen: raise SystemExit(f"python artifact is not hashed: {name}")
requirements=[name+"=="+artifacts[name]["version"] for name in sorted(artifacts)]
for table in ("dependencies","devDependencies"):
 if not doc.get("nodePackages",{}).get(table) or any(re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?",value) is None for value in doc["nodePackages"][table].values()): raise SystemExit("npm versions are not exact")
wheelhouse=member(doc["wheelhouse"],"wheelhouse","dir");cache=member(doc["npmCache"],"npmCache","dir");browser=member(doc["chromiumExecutable"],"chromiumExecutable","file");node=member(doc["nodeExecutable"],"nodeExecutable","file");npm=member(doc["npmExecutable"],"npmExecutable","file")
for label,path in (("wheelhouse",wheelhouse),("npmCache",cache),("artifacts",artifacts_root)):
 if any(path==other or path in other.parents or other in path.parents for other in (wheelhouse,cache,artifacts_root) if other!=path):raise SystemExit(f"{label} overlaps another support root")
for label,value in (("chromiumExecutable",doc["chromiumExecutable"]),("nodeExecutable",doc["nodeExecutable"]),("npmExecutable",doc["npmExecutable"])):
 if value not in seen: raise SystemExit(f"{label} is not hashed in files")
tables=doc["nodePackages"]
if (args.package is None)!=(args.package_lock is None):raise SystemExit("package and package-lock must be supplied together")
if args.package is not None:
 package=json.loads(args.package.resolve(strict=True).read_text("utf-8"));lock=json.loads(args.package_lock.resolve(strict=True).read_text("utf-8"));root_lock=lock.get("packages",{}).get("")
 if not isinstance(root_lock,dict) or lock.get("lockfileVersion")!=3:raise SystemExit("package lock root is invalid")
 for table in ("dependencies","devDependencies"):
  if package.get(table,{})!=tables[table] or root_lock.get(table,{})!=tables[table]:raise SystemExit(f"{table} differs from support manifest")
 for name,version in {**tables["dependencies"],**tables["devDependencies"]}.items():
  if lock["packages"].get("node_modules/"+name,{}).get("version")!=version:raise SystemExit(f"locked package version differs: {name}")
by_name={row["path"]:row for row in rows}
tree_hash=hashlib.sha256("".join(f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n" for row in sorted(rows,key=lambda row:row["path"])).encode("utf-8")).hexdigest()
print(json.dumps({"wheelhouse":str(wheelhouse),"npmCache":str(cache),"artifacts":str(artifacts_root),"browser":str(browser),"node":str(node),"npm":str(npm),"nodeSha256":by_name[doc["nodeExecutable"]]["sha256"],"npmSha256":by_name[doc["npmExecutable"]]["sha256"],"nodeVersion":doc["nodeVersion"],"npmVersion":doc["npmVersion"],"nodePackages":tables,"auditCache":bool(doc.get("npmAuditCache")),"pythonRequirements":requirements,"supportManifestSha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),"supportTreeSha256":tree_hash},separators=(",",":"),sort_keys=True))
