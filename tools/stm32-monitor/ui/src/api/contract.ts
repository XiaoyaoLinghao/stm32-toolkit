import {IntegerToken,encodeJson,i64,parseLossless} from "./wire";
export {i64} from "./wire";

export type I64=bigint;
export type JsonValue=null|boolean|number|bigint|string|readonly JsonValue[]|{readonly [k:string]:JsonValue};
export type ApiFailure={ok:false;code:string;message:string};
export type ApiResult<T>={ok:true;data:T}|ApiFailure;
export type ProjectStatus={logicalProjectId:string;name:string;targetDevice:string};
export type FirmwareStatus={buildId:string;elfSha256:string;inputSnapshotSha256:string;gitHead:string;gitDirty:boolean;targetDevice:string};
export type SamplingStatus={state:"IDLE"|"STARTING"|"RUNNING"|"PAUSED"|"PAUSED_BLOCKED"|"STOPPING";active:boolean;blockedCode:string|null;groupId:string|null;groupRevision:I64|null;runId:string|null;lastSequence:I64|null;bindingEpoch:I64;subscriberDrops:I64;historyDrops:I64;deadlineDrops:I64;serviceDrops:I64};
export type MonitorStatus={workspaceId:string;sessionId:string;project:ProjectStatus;firmware:FirmwareStatus|null;probe:{connected:boolean;probeId:string|null};sampling:SamplingStatus;probeConnected:boolean;samplingActive:boolean};
export type ProbeInfo={probeId:string;vendor:string;product:string;boardName:string|null};
export type VariableDescriptor={selector:string;typeName:string;kind:string;byteSize:number;signed:boolean|null;encoding:string|null;qualifiers:readonly string[];aliases:readonly string[];enumValues:readonly {value:bigint;name:string}[];elementCount:I64|null;elementKind:string|null;memberNames:readonly string[]};
export type RegisterDescriptor={selector:string;sizeBits:number;access:string|null;readAction:string|null;resetValue:bigint|null;resetMask:bigint|null;fields:readonly {name:string;bitOffset:number;bitWidth:number}[];sampleable:boolean;requiresAccessAcknowledgement:boolean};
export type CatalogGroup={id:string;label:string};
export type VariableCatalogItem=VariableDescriptor&{group:CatalogGroup};
export type RegisterCatalogItem=RegisterDescriptor&{group:CatalogGroup};
export type SourceReason="probe_required"|"source_mismatch"|"firmware_unavailable"|"frame_required"|"debug_entry_missing"|"ambiguous_symbol"|"unsupported_type"|"unsupported_location"|"read_range_denied"|"aggregate"|"coverage_incomplete"|"limit_reached"|"source_attribution_unproven";
export type SourceCatalogItem={id:string;parentId:string|null;name:string;typeName:string;file:string;line:number|null;column:number|null;scope:{kind:"global"|"file_static"|"static_local"|"local"|"parameter"|"member"|"element";function:string|null;path:readonly string[]};storage:"none"|"static"|"extern"|"register"|"thread_local";translationUnits:readonly string[];selector:string|null;canAdd:boolean;reason:SourceReason|null;expandable:boolean;truncated:boolean};
export type SourceCatalogPage={schemaVersion:1;catalogId:string;identity:{workspaceId:string;sessionId:string;logicalProjectId:string;targetDevice:string;sourceSnapshotSha256:string;buildId:string|null;elfSha256:string|null;bindingEpoch:I64};engine:{name:string;version:string;inputKind:"compdb"|"manifest"};coverage:{complete:boolean;totalUnits:number;parsedUnits:number;issues:readonly {unit:string|null;code:string;message:string}[];truncated:boolean;compiledDebug?:{available:boolean;variableCount:number;functionCount:number;fileCount:number}};total:number;items:readonly SourceCatalogItem[];nextCursor:string|null};
export type SourceFileNode={kind:"file";id:string;parentId:null;file:string;name:string;variableCount:number;scopeCount:number};
export type SourceScopeNode={kind:"scope";id:string;parentId:string;file:string;name:string;function:string|null;line:number|null;variableCount:number};
export type SourceTreeNode=SourceFileNode|SourceScopeNode;
export type SourceTreePage=Omit<SourceCatalogPage,"items">&{items:readonly SourceTreeNode[]};
export type SourceSelection={catalogId:string;item:VariableWatch};
export type VariableWatch={kind:"variable";expression:string};
export type RegisterWatch={kind:"register";registerPath:string};
export type WatchItem=VariableWatch|RegisterWatch;
export type WatchGroup={groupId:string;name:string;description:string;intervalMs:number;items:readonly WatchItem[];revision:I64;createdAtUtc:string;updatedAtUtc:string};
export type GroupPage={groups:readonly WatchGroup[];nextCursor:string|null;revision:string};
export type GroupTransfer={name:string;description:string;intervalMs:number;items:readonly WatchItem[]};
export type GroupImportDocument={schemaVersion:1;groups:readonly GroupTransfer[]};
export type MemoryRegionBinding={name:string;origin:number;length:number;attributes:string};
export type DebugFirmwareBinding={logicalProjectId:string;workspaceId:string;observationSessionId:string;flashSessionId:string;leaseId:string;probeId:string;targetDevice:string;debugTarget:string;buildId:string;elfSha256:string;elfSize:number;elfPath:string;inputSnapshotSha256:string;gitHead:string;gitDirty:boolean;confirmedAtUtc:string;memoryRegions:readonly MemoryRegionBinding[];svdReadableRegions:readonly MemoryRegionBinding[]};
export type ObservationBinding={workspaceId:string;logicalProjectId:string;sessionId:string;probeId:string;targetDevice:string;physicalTarget:string;buildId:string;elfSha256:string;inputSnapshotSha256:string;gitHead:string;gitDirty:boolean;flashSessionId:string;leaseId:string;dwarfSha256:string;svdSha256:string|null};
export type KnownTypedValue={expression:string;typeName:string;value:JsonValue;rawHex:string;bitWidth:number};
export type SampleValue={watch:WatchItem;status:"OK";typedValue:JsonValue;code:null;definition:Readonly<Record<string,JsonValue>>|null}|{watch:WatchItem;status:"ERROR";typedValue:null;code:string;definition:Readonly<Record<string,JsonValue>>|null};
export type SampleBatch={binding:ObservationBinding;groupId:string;groupRevision:I64;runId:string;sequence:I64;scheduledUnixNs:I64;scheduledAtUtc:string;capturedUnixNs:I64;capturedAtUtc:string;latencyNs:I64;actualRateHz:number;subscriberDrops:I64;historyDrops:I64;deadlineDrops:I64;values:readonly SampleValue[]};
export type LiveEvent={eventId:I64;type:"hello";data:{protocol:"stm32-toolkit-monitor/1";toolkitVersion:string;monitorVersion:string;stateRevision:I64}}|{eventId:I64;type:"state";data:{stateRevision:I64;gap:boolean;status:MonitorStatus}}|{eventId:I64;type:"sample";data:{batch:SampleBatch;serviceSubscriberDrops:I64}}|{eventId:I64;type:"heartbeat";data:{stateRevision:I64;capturedAtUtc:string}};
export type ParsedLiveEnvelope={event:LiveEvent;subscriberDropped:I64};
export type HistoryBatchSlice=SampleBatch&{startOrdinal:I64;batchValueCount:I64};
export type HistoryPage={batches:readonly HistoryBatchSlice[];valueCount:I64;nextCursor:string|null;serializedBytes:I64};
export type HistoryQuery={startNs:I64;endNs:I64;limit?:number;cursor?:string;runId?:string;groupId?:string;selectorKind?:"variable"|"register";selector?:string};
export type ExportArtifact={exportId:string;format:"csv"|"jsonl";sha256:string;bytes:I64;valueCount:I64};
export type GroupDraft={sourceGroupId:string|null;expectedRevision:I64|null;name:string;description:string;intervalMs:number;items:readonly WatchItem[]};
export type CreateGroupRequest=GroupTransfer&{authorized:true};
export type UpdateGroupRequest={expectedRevision:I64;authorized:true;name?:string;description?:string;intervalMs?:number;items?:readonly WatchItem[]};
export type DeleteGroupRequest={expectedRevision:I64;authorized:true};
export type SamplerStartResult={groupId:string;groupRevision:I64;runId:string;intervalMs:number};
export type DownloadResult=ApiFailure|{ok:true;blob:Blob;filename:string;contentType:string};
export interface MonitorApi{status():Promise<ApiResult<MonitorStatus>>;probes():Promise<ApiResult<{probes:readonly ProbeInfo[]}>>;
 variables(query:string,cursor?:string):Promise<ApiResult<{items:readonly VariableCatalogItem[];nextCursor:string|null}>>;registers(query:string,cursor?:string):Promise<ApiResult<{items:readonly RegisterCatalogItem[];nextCursor:string|null}>>;
 sourceTree(query:string,cursor?:string,parentId?:string,catalogId?:string,refresh?:boolean):Promise<ApiResult<SourceTreePage>>;
 sourceVariables(query:string,cursor?:string,parentId?:string,catalogId?:string,scopeId?:string):Promise<ApiResult<SourceCatalogPage>>;sourceSelection(catalogId:string,id:string,selector:string):Promise<ApiResult<SourceSelection>>;
 groups(cursor?:string):Promise<ApiResult<GroupPage>>;createGroup(request:CreateGroupRequest):Promise<ApiResult<WatchGroup>>;updateGroup(groupId:string,request:UpdateGroupRequest):Promise<ApiResult<WatchGroup>>;deleteGroup(groupId:string,request:DeleteGroupRequest):Promise<ApiResult<{groupId:string;deleted:true}>>;importGroups(document:GroupImportDocument):Promise<ApiResult<readonly WatchGroup[]>>;
 connect(probeId:string):Promise<ApiResult<DebugFirmwareBinding>>;reconnect():Promise<ApiResult<DebugFirmwareBinding>>;release():Promise<ApiResult<{released:boolean}>>;
 start(groupId:string,expectedRevision:I64):Promise<ApiResult<SamplerStartResult>>;pause():Promise<ApiResult<{paused:boolean}>>;resume():Promise<ApiResult<{resumed:boolean}>>;stop():Promise<ApiResult<{stopped:boolean}>>;
 history(query:HistoryQuery):Promise<ApiResult<HistoryPage>>;createExport(startNs:I64,endNs:I64,format:"csv"|"jsonl"):Promise<ApiResult<ExportArtifact>>;exportStatus(exportId:string):Promise<ApiResult<ExportArtifact>>;downloadExport(exportId:string):Promise<DownloadResult>}
export type LiveHandlers={onOpen():void;onEnvelope(value:ParsedLiveEnvelope):void;onFailed():void;onClosed():void};
export type OpenLive=(afterEventId:I64|null,handlers:LiveHandlers)=>(()=>void);
export type DataGuard<T>=(value:unknown)=>T;

type RecordValue=Record<string,unknown>;
const object=(value:unknown):RecordValue=>{if(value===null||typeof value!=="object"||Array.isArray(value))throw new Error("expected object");return value as RecordValue;};
const exact=(value:RecordValue,keys:readonly string[])=>{const actual=Object.keys(value);if(actual.length!==keys.length||actual.some(key=>!keys.includes(key)))throw new Error("unexpected object shape");};
const string=(value:unknown):string=>{if(typeof value!=="string")throw new Error("expected string");return value;};
const boolean=(value:unknown):boolean=>{if(typeof value!=="boolean")throw new Error("expected boolean");return value;};
const nullable=<T>(value:unknown,guard:DataGuard<T>):T|null=>value===null?null:guard(value);
const array=<T>(value:unknown,guard:DataGuard<T>):readonly T[]=>{if(!Array.isArray(value))throw new Error("expected array");return value.map(guard);};
const boundedInteger=(value:unknown):number=>{if(!(value instanceof IntegerToken))throw new Error("expected integer");const result=Number(value.decimal);if(!Number.isSafeInteger(result))throw new Error("integer outside safe range");return result;};
const number=(value:unknown):number=>{if(typeof value!=="number"||!Number.isFinite(value))throw new Error("expected finite number");return value;};
const literal=<T extends string|boolean|number>(expected:T)=>(value:unknown):T=>{const actual=typeof expected==="number"?boundedInteger(value):value;if(actual!==expected)throw new Error("unexpected literal");return expected;};
const enumValue=<T extends string>(values:readonly T[],value:unknown):T=>{const actual=string(value);if(!values.includes(actual as T))throw new Error("unexpected enum");return actual as T;};
const stringArray=(value:unknown)=>array(value,string);
const integerToken=/^-?(?:0|[1-9]\d*)$/;
const bigintInteger=(value:unknown):bigint=>{if(!(value instanceof IntegerToken)||!integerToken.test(value.decimal))throw new Error("expected integer");return BigInt(value.decimal);};
const nonnegativeBigint=(value:unknown):bigint=>{const result=bigintInteger(value);if(result<0n)throw new Error("expected nonnegative integer");return result;};
const nullRecord=():Record<string,JsonValue>=>Object.create(null) as Record<string,JsonValue>;
const jsonValueGuard=(value:unknown):JsonValue=>{if(value===null||typeof value==="string"||typeof value==="boolean")return value;if(typeof value==="number"){if(!Number.isFinite(value))throw new Error("invalid JSON number");return value;}if(value instanceof IntegerToken){const converted=BigInt(value.decimal);return converted>=BigInt(Number.MIN_SAFE_INTEGER)&&converted<=BigInt(Number.MAX_SAFE_INTEGER)?Number(converted):converted;}if(Array.isArray(value))return value.map(jsonValueGuard);const record=object(value),result=nullRecord();for(const [key,item] of Object.entries(record))result[key]=jsonValueGuard(item);return result;};
const jsonRecordGuard=(value:unknown):Readonly<Record<string,JsonValue>>=>{const record=object(value),result=nullRecord();for(const [key,item] of Object.entries(record))result[key]=jsonValueGuard(item);return result;};

export const projectStatusGuard:DataGuard<ProjectStatus>=(value)=>{const v=object(value);exact(v,["logicalProjectId","name","targetDevice"]);return{logicalProjectId:string(v.logicalProjectId),name:string(v.name),targetDevice:string(v.targetDevice)};};
export const firmwareStatusGuard:DataGuard<FirmwareStatus>=(value)=>{const v=object(value);exact(v,["buildId","elfSha256","inputSnapshotSha256","gitHead","gitDirty","targetDevice"]);return{buildId:string(v.buildId),elfSha256:string(v.elfSha256),inputSnapshotSha256:string(v.inputSnapshotSha256),gitHead:string(v.gitHead),gitDirty:boolean(v.gitDirty),targetDevice:string(v.targetDevice)};};
export const samplingStatusGuard:DataGuard<SamplingStatus>=(value)=>{const v=object(value);exact(v,["state","active","blockedCode","groupId","groupRevision","runId","lastSequence","bindingEpoch","subscriberDrops","historyDrops","deadlineDrops","serviceDrops"]);return{state:enumValue(["IDLE","STARTING","RUNNING","PAUSED","PAUSED_BLOCKED","STOPPING"],v.state),active:boolean(v.active),blockedCode:nullable(v.blockedCode,string),groupId:nullable(v.groupId,string),groupRevision:nullable(v.groupRevision,i64),runId:nullable(v.runId,string),lastSequence:nullable(v.lastSequence,i64),bindingEpoch:i64(v.bindingEpoch),subscriberDrops:i64(v.subscriberDrops),historyDrops:i64(v.historyDrops),deadlineDrops:i64(v.deadlineDrops),serviceDrops:i64(v.serviceDrops)};};
export const monitorStatusGuard:DataGuard<MonitorStatus>=(value)=>{const v=object(value);exact(v,["workspaceId","sessionId","project","firmware","probe","sampling","probeConnected","samplingActive"]);const p=object(v.probe);exact(p,["connected","probeId"]);return{workspaceId:string(v.workspaceId),sessionId:string(v.sessionId),project:projectStatusGuard(v.project),firmware:nullable(v.firmware,firmwareStatusGuard),probe:{connected:boolean(p.connected),probeId:nullable(p.probeId,string)},sampling:samplingStatusGuard(v.sampling),probeConnected:boolean(v.probeConnected),samplingActive:boolean(v.samplingActive)};};
export const probeInfoGuard:DataGuard<ProbeInfo>=(value)=>{const v=object(value);exact(v,["probeId","vendor","product","boardName"]);return{probeId:string(v.probeId),vendor:string(v.vendor),product:string(v.product),boardName:nullable(v.boardName,string)};};
export const variableDescriptorGuard:DataGuard<VariableDescriptor>=(value)=>{const v=object(value);exact(v,["selector","typeName","kind","byteSize","signed","encoding","qualifiers","aliases","enumValues","elementCount","elementKind","memberNames"]);return{selector:string(v.selector),typeName:string(v.typeName),kind:string(v.kind),byteSize:boundedInteger(v.byteSize),signed:nullable(v.signed,boolean),encoding:nullable(v.encoding,string),qualifiers:stringArray(v.qualifiers),aliases:stringArray(v.aliases),enumValues:array(v.enumValues,item=>{const e=object(item);exact(e,["value","name"]);return{value:bigintInteger(e.value),name:string(e.name)};}),elementCount:nullable(v.elementCount,i64),elementKind:nullable(v.elementKind,string),memberNames:stringArray(v.memberNames)};};
export const registerDescriptorGuard:DataGuard<RegisterDescriptor>=(value)=>{const v=object(value);exact(v,["selector","sizeBits","access","readAction","resetValue","resetMask","fields","sampleable","requiresAccessAcknowledgement"]);return{selector:string(v.selector),sizeBits:boundedInteger(v.sizeBits),access:nullable(v.access,string),readAction:nullable(v.readAction,string),resetValue:nullable(v.resetValue,nonnegativeBigint),resetMask:nullable(v.resetMask,nonnegativeBigint),fields:array(v.fields,item=>{const f=object(item);exact(f,["name","bitOffset","bitWidth"]);return{name:string(f.name),bitOffset:boundedInteger(f.bitOffset),bitWidth:boundedInteger(f.bitWidth)};}),sampleable:boolean(v.sampleable),requiresAccessAcknowledgement:boolean(v.requiresAccessAcknowledgement)};};
export const catalogGroupGuard:DataGuard<CatalogGroup>=(value)=>{
  const v=object(value);exact(v,["id","label"]);
  const id=string(v.id),label=string(v.label);
  if(!/^[A-Za-z0-9:_-]{1,128}$/.test(id)||label.length<1||label.length>512||!label.trim()||
    /[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(label)||label.startsWith("/")||label.startsWith("\\")||
    /^[A-Za-z]:[\\/]/.test(label)||label.replaceAll("\\","/").split("/").some(component=>component==="."||component===".."))
    throw new Error("invalid catalog group");
  return{id,label};
};
export const variableCatalogItemGuard:DataGuard<VariableCatalogItem>=(value)=>{
  const v=object(value),{group,...descriptor}=v;
  return{...variableDescriptorGuard(descriptor),group:catalogGroupGuard(group)};
};
export const registerCatalogItemGuard:DataGuard<RegisterCatalogItem>=(value)=>{
  const v=object(value),{group,...descriptor}=v;
  return{...registerDescriptorGuard(descriptor),group:catalogGroupGuard(group)};
};
const sha256=(value:unknown):string=>{const result=string(value);if(!/^[0-9a-f]{64}$/.test(result))throw new Error("invalid identity");return result;};
const relativeFile=(value:unknown):string=>{const result=string(value);if(!result||result.length>512||result.startsWith("/")||result.startsWith("\\")||/^[A-Za-z]:/.test(result)||result.split(/[\\/]/).some(part=>!part||part==="."||part==="..")||[...result].some(char=>char.charCodeAt(0)<32))throw new Error("invalid source path");return result;};
const positive=(value:unknown):number=>{const result=boundedInteger(value);if(result<1)throw new Error("expected positive integer");return result;};
const nonnegative=(value:unknown):number=>{const result=boundedInteger(value);if(result<0)throw new Error("expected nonnegative integer");return result;};
const sourceCursor=(value:unknown):string=>{const result=string(value);if(!result||result.length>2048)throw new Error("invalid source cursor");return result;};
const reasonValues=["probe_required","source_mismatch","firmware_unavailable","frame_required","debug_entry_missing","ambiguous_symbol","unsupported_type","unsupported_location","read_range_denied","aggregate","coverage_incomplete","limit_reached","source_attribution_unproven"] as const;
export const sourceCatalogItemGuard:DataGuard<SourceCatalogItem>=(value)=>{
 const v=object(value);exact(v,["id","parentId","name","typeName","file","line","column","scope","storage","translationUnits","selector","canAdd","reason","expandable","truncated"]);
 const s=object(v.scope);exact(s,["kind","function","path"]);
 const item:SourceCatalogItem={id:sha256(v.id),parentId:nullable(v.parentId,sha256),name:string(v.name),typeName:string(v.typeName),file:relativeFile(v.file),line:nullable(v.line,positive),column:nullable(v.column,positive),scope:{kind:enumValue(["global","file_static","static_local","local","parameter","member","element"],s.kind),function:nullable(s.function,string),path:stringArray(s.path)},storage:enumValue(["none","static","extern","register","thread_local"],v.storage),translationUnits:array(v.translationUnits,relativeFile),selector:nullable(v.selector,string),canAdd:boolean(v.canAdd),reason:nullable(v.reason,value=>enumValue(reasonValues,value)),expandable:boolean(v.expandable),truncated:boolean(v.truncated)};
 if(!item.name||item.name.length>256||item.typeName.length>512||item.translationUnits.length>256||item.scope.path.length>64||item.canAdd&&(item.selector===null||item.reason!==null)||item.reason===null&&!item.canAdd)throw new Error("invalid source item");
 return item;
};
export const sourceCatalogPageGuard:DataGuard<SourceCatalogPage>=(value)=>{
 const v=object(value);exact(v,["schemaVersion","catalogId","identity","engine","coverage","total","items","nextCursor"]);
 const i=object(v.identity);exact(i,["workspaceId","sessionId","logicalProjectId","targetDevice","sourceSnapshotSha256","buildId","elfSha256","bindingEpoch"]);
 const e=object(v.engine);exact(e,["name","version","inputKind"]);
 const c=object(v.coverage);const hasCompiledDebug=Object.hasOwn(c,"compiledDebug");exact(c,hasCompiledDebug?["complete","totalUnits","parsedUnits","issues","truncated","compiledDebug"]:["complete","totalUnits","parsedUnits","issues","truncated"]);
 const compiledDebug=hasCompiledDebug?object(c.compiledDebug):null;
 if(compiledDebug!==null)exact(compiledDebug,["available","variableCount","functionCount","fileCount"]);
 const items=array(v.items,sourceCatalogItemGuard),ids=new Set<string>();for(const item of items){if(ids.has(item.id))throw new Error("duplicate source id");ids.add(item.id);}
 const total=nonnegative(v.total),totalUnits=nonnegative(c.totalUnits),parsedUnits=nonnegative(c.parsedUnits);
 if(items.length>100||total<items.length||parsedUnits>totalUnits||Boolean(c.complete)&&Boolean(c.truncated)||!string(e.name)||!string(e.version))throw new Error("invalid source page");
 return{schemaVersion:literal(1)(v.schemaVersion),catalogId:sha256(v.catalogId),identity:{workspaceId:string(i.workspaceId),sessionId:string(i.sessionId),logicalProjectId:string(i.logicalProjectId),targetDevice:string(i.targetDevice),sourceSnapshotSha256:sha256(i.sourceSnapshotSha256),buildId:nullable(i.buildId,string),elfSha256:nullable(i.elfSha256,sha256),bindingEpoch:i64(i.bindingEpoch)},engine:{name:string(e.name),version:string(e.version),inputKind:enumValue(["compdb","manifest"],e.inputKind)},coverage:{complete:boolean(c.complete),totalUnits,parsedUnits,issues:array(c.issues,item=>{const issue=object(item);exact(issue,["unit","code","message"]);return{unit:nullable(issue.unit,relativeFile),code:string(issue.code),message:string(issue.message)};}),truncated:boolean(c.truncated),...(compiledDebug===null?{}:{compiledDebug:{available:boolean(compiledDebug.available),variableCount:nonnegative(compiledDebug.variableCount),functionCount:nonnegative(compiledDebug.functionCount),fileCount:nonnegative(compiledDebug.fileCount)}})},total,items,nextCursor:nullable(v.nextCursor,sourceCursor)};
};
export const sourceTreeNodeGuard:DataGuard<SourceTreeNode>=(value)=>{
 const v=object(value),kind=string(v.kind),name=string(v.name),file=relativeFile(v.file);
 if(!name||name.length>256)throw new Error("invalid source tree name");
 if(kind==="file"){
  exact(v,["kind","id","parentId","file","name","variableCount","scopeCount"]);
  if(v.parentId!==null||name!==file.split("/").at(-1))throw new Error("invalid source file node");
  return{kind:"file",id:sha256(v.id),parentId:null,file,name,
    variableCount:nonnegative(v.variableCount),scopeCount:nonnegative(v.scopeCount)};
 }
 if(kind==="scope"){
  exact(v,["kind","id","parentId","file","name","function","line","variableCount"]);
  const functionName=nullable(v.function,string),line=nullable(v.line,positive);
  if(functionName===null?name!=="global"||line!==null:name!==functionName)throw new Error("invalid source scope node");
  return{kind:"scope",id:sha256(v.id),parentId:sha256(v.parentId),file,name,function:functionName,line,
    variableCount:nonnegative(v.variableCount)};
 }
 throw new Error("invalid source tree kind");
};
export const sourceTreePageGuard:DataGuard<SourceTreePage>=(value)=>{
 const v=object(value),base=sourceCatalogPageGuard({...v,items:[]});
 const items=array(v.items,sourceTreeNodeGuard),seen=new Set<string>();
 if(items.length>1000||base.total<items.length)throw new Error("invalid source tree page");
 for(const item of items){if(seen.has(item.id))throw new Error("duplicate source tree id");seen.add(item.id);}
 return{...base,items};
};
export const sourceSelectionGuard:DataGuard<SourceSelection>=(value)=>{const v=object(value);exact(v,["catalogId","item"]);const item=watchItemGuard(v.item);if(item.kind!=="variable")throw new Error("source selection must be variable");return{catalogId:sha256(v.catalogId),item};};
function catalogItems<T extends {selector:string;group:CatalogGroup}>(value:unknown,guard:DataGuard<T>):readonly T[]{
  const items=array(value,guard),labels=new Map<string,string>(),selectors=new Map<string,T>();
  for(const item of items){
    const label=labels.get(item.group.id),prior=selectors.get(item.selector);
    if(label!==undefined&&label!==item.group.label||prior!==undefined&&encodeJson(prior)!==encodeJson(item))
      throw new Error("conflicting catalog page");
    labels.set(item.group.id,item.group.label);selectors.set(item.selector,item);
  }
  return items;
}
export const watchItemGuard:DataGuard<WatchItem>=(value)=>{const v=object(value),kind=string(v.kind);if(kind==="variable"){exact(v,["kind","expression"]);return{kind:"variable",expression:string(v.expression)};}if(kind==="register"){exact(v,["kind","registerPath"]);return{kind:"register",registerPath:string(v.registerPath)};}throw new Error("unknown watch kind");};
export const watchGroupGuard:DataGuard<WatchGroup>=(value)=>{const v=object(value);exact(v,["groupId","name","description","intervalMs","items","revision","createdAtUtc","updatedAtUtc"]);return{groupId:string(v.groupId),name:string(v.name),description:string(v.description),intervalMs:boundedInteger(v.intervalMs),items:array(v.items,watchItemGuard),revision:i64(v.revision),createdAtUtc:string(v.createdAtUtc),updatedAtUtc:string(v.updatedAtUtc)};};
export const groupPageGuard:DataGuard<GroupPage>=(value)=>{const v=object(value);exact(v,["groups","nextCursor","revision"]);return{groups:array(v.groups,watchGroupGuard),nextCursor:nullable(v.nextCursor,string),revision:string(v.revision)};};
export const groupTransferGuard:DataGuard<GroupTransfer>=(value)=>{const v=object(value);exact(v,["name","description","intervalMs","items"]);return{name:string(v.name),description:string(v.description),intervalMs:boundedInteger(v.intervalMs),items:array(v.items,watchItemGuard)};};
export const groupImportGuard:DataGuard<GroupImportDocument>=(value)=>{const v=object(value);exact(v,["schemaVersion","groups"]);return{schemaVersion:literal(1)(v.schemaVersion),groups:array(v.groups,groupTransferGuard)};};
export const memoryRegionBindingGuard:DataGuard<MemoryRegionBinding>=(value)=>{const v=object(value);exact(v,["name","origin","length","attributes"]);return{name:string(v.name),origin:boundedInteger(v.origin),length:boundedInteger(v.length),attributes:string(v.attributes)};};
export const debugFirmwareBindingGuard:DataGuard<DebugFirmwareBinding>=(value)=>{
  const v=object(value);
  exact(v,["logicalProjectId","workspaceId","observationSessionId","flashSessionId","leaseId","probeId","targetDevice","debugTarget","buildId","elfSha256","elfSize","elfPath","inputSnapshotSha256","gitHead","gitDirty","confirmedAtUtc","memoryRegions","svdReadableRegions"]);
  const svdReadableRegions=array(v.svdReadableRegions,memoryRegionBindingGuard);
  if(svdReadableRegions.length===0)throw new Error("expected non-empty readable regions");
  return{logicalProjectId:string(v.logicalProjectId),workspaceId:string(v.workspaceId),observationSessionId:string(v.observationSessionId),flashSessionId:string(v.flashSessionId),leaseId:string(v.leaseId),probeId:string(v.probeId),targetDevice:string(v.targetDevice),debugTarget:string(v.debugTarget),buildId:string(v.buildId),elfSha256:string(v.elfSha256),elfSize:boundedInteger(v.elfSize),elfPath:string(v.elfPath),inputSnapshotSha256:string(v.inputSnapshotSha256),gitHead:string(v.gitHead),gitDirty:boolean(v.gitDirty),confirmedAtUtc:string(v.confirmedAtUtc),memoryRegions:array(v.memoryRegions,memoryRegionBindingGuard),svdReadableRegions};
};
export const observationBindingGuard:DataGuard<ObservationBinding>=(value)=>{const v=object(value);exact(v,["workspaceId","logicalProjectId","sessionId","probeId","targetDevice","physicalTarget","buildId","elfSha256","inputSnapshotSha256","gitHead","gitDirty","flashSessionId","leaseId","dwarfSha256","svdSha256"]);return{workspaceId:string(v.workspaceId),logicalProjectId:string(v.logicalProjectId),sessionId:string(v.sessionId),probeId:string(v.probeId),targetDevice:string(v.targetDevice),physicalTarget:string(v.physicalTarget),buildId:string(v.buildId),elfSha256:string(v.elfSha256),inputSnapshotSha256:string(v.inputSnapshotSha256),gitHead:string(v.gitHead),gitDirty:boolean(v.gitDirty),flashSessionId:string(v.flashSessionId),leaseId:string(v.leaseId),dwarfSha256:string(v.dwarfSha256),svdSha256:nullable(v.svdSha256,string)};};
export const knownTypedValue=(value:JsonValue):KnownTypedValue|null=>{try{const v=object(value);exact(v,["expression","typeName","value","rawHex","bitWidth"]);return{expression:string(v.expression),typeName:string(v.typeName),value:jsonValueGuard(v.value),rawHex:string(v.rawHex),bitWidth:typeof v.bitWidth==="bigint"?Number(v.bitWidth):number(v.bitWidth)};}catch{return null;}};
export const sampleValueGuard:DataGuard<SampleValue>=(value)=>{const v=object(value);exact(v,["watch","status","typedValue","code","definition"]);const definition=nullable(v.definition,jsonRecordGuard);if(v.status==="OK"){if(v.code!==null)throw new Error("OK sample has code");return{watch:watchItemGuard(v.watch),status:"OK",typedValue:jsonValueGuard(v.typedValue),code:null,definition};}if(v.status==="ERROR"){if(v.typedValue!==null)throw new Error("ERROR sample has value");return{watch:watchItemGuard(v.watch),status:"ERROR",typedValue:null,code:string(v.code),definition};}throw new Error("unknown sample status");};
export const sampleBatchGuard:DataGuard<SampleBatch>=(value)=>{const v=object(value);exact(v,["binding","groupId","groupRevision","runId","sequence","scheduledUnixNs","scheduledAtUtc","capturedUnixNs","capturedAtUtc","latencyNs","actualRateHz","subscriberDrops","historyDrops","deadlineDrops","values"]);return{binding:observationBindingGuard(v.binding),groupId:string(v.groupId),groupRevision:i64(v.groupRevision),runId:string(v.runId),sequence:i64(v.sequence),scheduledUnixNs:i64(v.scheduledUnixNs),scheduledAtUtc:string(v.scheduledAtUtc),capturedUnixNs:i64(v.capturedUnixNs),capturedAtUtc:string(v.capturedAtUtc),latencyNs:i64(v.latencyNs),actualRateHz:number(v.actualRateHz),subscriberDrops:i64(v.subscriberDrops),historyDrops:i64(v.historyDrops),deadlineDrops:i64(v.deadlineDrops),values:array(v.values,sampleValueGuard)};};
export const liveEventGuard:DataGuard<LiveEvent>=(value)=>{const v=object(value);exact(v,["eventId","type","data"]);const eventId=i64(v.eventId),data=object(v.data),type=string(v.type);if(type==="hello"){exact(data,["protocol","toolkitVersion","monitorVersion","stateRevision"]);return{eventId,type,data:{protocol:literal("stm32-toolkit-monitor/1")(data.protocol),toolkitVersion:string(data.toolkitVersion),monitorVersion:string(data.monitorVersion),stateRevision:i64(data.stateRevision)}};}if(type==="state"){exact(data,["stateRevision","gap","status"]);return{eventId,type,data:{stateRevision:i64(data.stateRevision),gap:boolean(data.gap),status:monitorStatusGuard(data.status)}};}if(type==="sample"){exact(data,["batch","serviceSubscriberDrops"]);return{eventId,type,data:{batch:sampleBatchGuard(data.batch),serviceSubscriberDrops:i64(data.serviceSubscriberDrops)}};}if(type==="heartbeat"){exact(data,["stateRevision","capturedAtUtc"]);return{eventId,type,data:{stateRevision:i64(data.stateRevision),capturedAtUtc:string(data.capturedAtUtc)}};}throw new Error("unknown live event");};
export const historyBatchSliceGuard:DataGuard<HistoryBatchSlice>=(value)=>{const v=object(value);exact(v,["binding","groupId","groupRevision","runId","sequence","scheduledUnixNs","scheduledAtUtc","capturedUnixNs","capturedAtUtc","latencyNs","actualRateHz","subscriberDrops","historyDrops","deadlineDrops","values","startOrdinal","batchValueCount"]);return{binding:observationBindingGuard(v.binding),groupId:string(v.groupId),groupRevision:i64(v.groupRevision),runId:string(v.runId),sequence:i64(v.sequence),scheduledUnixNs:i64(v.scheduledUnixNs),scheduledAtUtc:string(v.scheduledAtUtc),capturedUnixNs:i64(v.capturedUnixNs),capturedAtUtc:string(v.capturedAtUtc),latencyNs:i64(v.latencyNs),actualRateHz:number(v.actualRateHz),subscriberDrops:i64(v.subscriberDrops),historyDrops:i64(v.historyDrops),deadlineDrops:i64(v.deadlineDrops),values:array(v.values,sampleValueGuard),startOrdinal:i64(v.startOrdinal),batchValueCount:i64(v.batchValueCount)};};
export const historyPageGuard:DataGuard<HistoryPage>=(value)=>{const v=object(value);exact(v,["batches","valueCount","nextCursor","serializedBytes"]);return{batches:array(v.batches,historyBatchSliceGuard),valueCount:i64(v.valueCount),nextCursor:nullable(v.nextCursor,string),serializedBytes:i64(v.serializedBytes)};};
export const exportArtifactGuard:DataGuard<ExportArtifact>=(value)=>{const v=object(value);exact(v,["exportId","format","sha256","bytes","valueCount"]);return{exportId:string(v.exportId),format:enumValue(["csv","jsonl"],v.format),sha256:string(v.sha256),bytes:i64(v.bytes),valueCount:i64(v.valueCount)};};

export const probesGuard:DataGuard<{probes:readonly ProbeInfo[]}>=(value)=>{const v=object(value);exact(v,["probes"]);return{probes:array(v.probes,probeInfoGuard)};};
export const variablesGuard:DataGuard<{items:readonly VariableCatalogItem[];nextCursor:string|null}>=(value)=>{const v=object(value);exact(v,["items","nextCursor"]);return{items:catalogItems(v.items,variableCatalogItemGuard),nextCursor:nullable(v.nextCursor,string)};};
export const registersGuard:DataGuard<{items:readonly RegisterCatalogItem[];nextCursor:string|null}>=(value)=>{const v=object(value);exact(v,["items","nextCursor"]);return{items:catalogItems(v.items,registerCatalogItemGuard),nextCursor:nullable(v.nextCursor,string)};};
export const watchGroupsGuard:DataGuard<readonly WatchGroup[]>=(value)=>array(value,watchGroupGuard);
export const deletedGroupGuard:DataGuard<{groupId:string;deleted:true}>=(value)=>{const v=object(value);exact(v,["groupId","deleted"]);return{groupId:string(v.groupId),deleted:literal(true)(v.deleted)};};
export const releasedGuard:DataGuard<{released:boolean}>=(value)=>{const v=object(value);exact(v,["released"]);return{released:boolean(v.released)};};
export const samplerStartGuard:DataGuard<SamplerStartResult>=(value)=>{const v=object(value);exact(v,["groupId","groupRevision","runId","intervalMs"]);return{groupId:string(v.groupId),groupRevision:i64(v.groupRevision),runId:string(v.runId),intervalMs:boundedInteger(v.intervalMs)};};
const booleanResult=(key:string)=>(value:unknown)=>{const v=object(value);exact(v,[key]);return boolean(v[key]);};
export const pausedGuard:DataGuard<{paused:boolean}>=(value)=>({paused:booleanResult("paused")(value)});
export const resumedGuard:DataGuard<{resumed:boolean}>=(value)=>({resumed:booleanResult("resumed")(value)});
export const stoppedGuard:DataGuard<{stopped:boolean}>=(value)=>({stopped:booleanResult("stopped")(value)});

const detailsSymbol=Symbol("envelope-details");
type ResultWithDetails<T>=ApiResult<T>&{[detailsSymbol]?:RecordValue};
export function envelopeDetails<T>(result:ApiResult<T>):RecordValue{const details=(result as ResultWithDetails<T>)[detailsSymbol];if(details===undefined)throw new Error("envelope details unavailable");return details;}
export function parseEnvelope<T>(text:string,operation:string,guard:DataGuard<T>):ApiResult<T>{try{const value=parseLossless(text),v=object(value);exact(v,["protocol","toolkitVersion","monitorVersion","ok","operation","code","message","data","details"]);literal("stm32-toolkit-monitor/1")(v.protocol);string(v.toolkitVersion);string(v.monitorVersion);if(string(v.operation)!==operation)throw new Error("unexpected operation");const ok=boolean(v.ok),code=string(v.code),message=string(v.message),details=object(v.details);if(ok){if(code!=="OK"||message!=="")throw new Error("success envelope is inconsistent");const result:ResultWithDetails<T>={ok:true,data:guard(v.data)};Object.defineProperty(result,detailsSymbol,{value:details});return result;}if(code==="OK"||message===""||v.data!==null)throw new Error("failure envelope is inconsistent");const result:ResultWithDetails<T>={ok:false,code,message};Object.defineProperty(result,detailsSymbol,{value:details});return result;}catch{return{ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"};}}
export const authenticatedGuard:DataGuard<{authenticated:true}>=(value)=>{const v=object(value);exact(v,["authenticated"]);literal(true)(v.authenticated);return{authenticated:true};};
export function parseEnvelopeText<T>(text:string,operation:string,guard:DataGuard<T>):ApiResult<T>{return parseEnvelope(text,operation,guard);}
