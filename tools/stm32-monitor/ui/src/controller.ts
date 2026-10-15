import {
  groupImportGuard,
  type ApiFailure,type ApiResult,type GroupDraft,type GroupImportDocument,type MonitorStatus,
  type HistoryQuery,type MonitorApi,type WatchGroup,type WatchItem,
} from "./api/contract";
import {parseLossless} from "./api/wire";
import {openLive} from "./api/live";
import {operationSummary} from "./presentation/zh";
import {groupSourceProblem,sameGroupContent,type LoadedAction,type MonitorAction,type MonitorState,type RecoveryKind,type RequestScope} from "./state/model";

export type Controller={
  loadInitial:()=>Promise<void>;refreshStatus:()=>Promise<void>;reconnectLive:()=>Promise<void>;cancelLiveReconnect:()=>void;refreshProbes:()=>Promise<void>;refreshGroups:()=>Promise<void>;
  connectProbe:(probeId:string)=>Promise<void>;reconnectProbe:()=>Promise<void>;releaseProbe:()=>Promise<void>;
  searchCatalog:(kind:"variables"|"registers",query:string)=>Promise<void>;
  nextCatalog:(kind:"variables"|"registers")=>Promise<void>;
  createGroup:()=>Promise<void>;saveGroup:(draft:GroupDraft)=>Promise<void>;deleteGroup:(groupId:string,expectedRevision?:bigint,editorGeneration?:bigint)=>Promise<void>;
  importGroups:(value:unknown)=>Promise<void>;
  startSampling:(groupId:string,expectedRevision:bigint)=>Promise<void>;
  pauseSampling:()=>Promise<void>;resumeSampling:()=>Promise<void>;stopSampling:()=>Promise<void>;
  loadHistory:(query:HistoryQuery)=>Promise<void>;nextHistory:(cursor:string|undefined)=>Promise<void>;
  createExport:(startNs:bigint,endNs:bigint,format:"csv"|"jsonl")=>Promise<void>;
  refreshExport:(exportId:string)=>Promise<void>;downloadExport:(exportId:string)=>Promise<void>;
  retry:(scope:RequestScope,requestId:bigint)=>Promise<void>;dismiss:(scope:RequestScope,requestId:bigint)=>void;
  close:()=>void;
};
const cloneWatch=(item:WatchItem):WatchItem=>item.kind==="variable"
  ?{kind:"variable",expression:item.expression}:{kind:"register",registerPath:item.registerPath};
const cloneDraft=(draft:GroupDraft):GroupDraft=>({...draft,items:draft.items.map(cloneWatch)});
const sameDraft=(left:GroupDraft,right:GroupDraft):boolean=>left.sourceGroupId===right.sourceGroupId&&left.expectedRevision===right.expectedRevision&&sameGroupContent(left,right);
const cloneImport=(doc:GroupImportDocument):GroupImportDocument=>({schemaVersion:1,
  groups:doc.groups.map(group=>({...group,items:group.items.map(cloneWatch)}))});
const unexpected=(error:unknown):ApiFailure=>({ok:false,code:"MONITOR_TRANSPORT_FAILED",
  message:error instanceof Error?error.message:String(error)});
const fatalCode=(code:string)=>[
  "MONITOR_AUTH_REQUIRED","MONITOR_PEER_REJECTED","MONITOR_HOST_REJECTED",
  "MONITOR_ORIGIN_REJECTED","MONITOR_SESSION_EXPIRED","MONITOR_ACCESS_REJECTED",
].includes(code);
const uncertainCode=(code:string)=>code==="MONITOR_TRANSPORT_FAILED"||code==="MONITOR_RESPONSE_INVALID";
const groupConflictCode=(code:string)=>["MONITOR_GROUP_CONFLICT","MONITOR_GROUP_NOT_FOUND","MONITOR_IMPORT_CONFLICT"].includes(code);
const groupInputCode=(code:string)=>["MONITOR_REQUEST_INVALID","MONITOR_GROUP_LIMIT_EXCEEDED","MONITOR_IMPORT_INVALID"].includes(code);
function parseGroupImport(value:unknown):ApiResult<GroupImportDocument>{
  try{return{ok:true,data:groupImportGuard(value)};}catch{/* In-memory document path. */}
  try{return{ok:true,data:groupImportGuard(parseLossless(JSON.stringify(value)))};}
  catch{return{ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import document is invalid"};}
}
type Retry={requestId:bigint;recovery:RecoveryKind;run:()=>Promise<void>;valid?:()=>boolean};
type Family="groups"|"probe"|"sampling"|"export";

export function createController(api:MonitorApi,dispatch:(action:MonitorAction)=>void,getState:()=>MonitorState):Controller{
  let nextId=1n,closed=false,blocked=false,initialized=false,lifecycle=0,latestInitialId:bigint|null=null;
  let closeLive:(()=>void)|null=null,liveGeneration=0,connectingInitial=false;
  let workbenchIdentity:{workspaceId:string;sessionId:string;logicalProjectId:string}|null=null;
  const active=new Map<RequestScope,bigint>();
  const retries=new Map<RequestScope,Retry>();
  const writing=new Set<Family>();
  const reconciling=new Set<RequestScope>();
  const retireLive=():void=>{
    liveGeneration++;connectingInitial=false;
    const close=closeLive;closeLive=null;
    close?.();
  };
  const liveBusy=()=>connectingInitial||active.has("live.reconnect");
  const sameWorkbench=(status:MonitorStatus):boolean=>workbenchIdentity===null||
    status.workspaceId===workbenchIdentity.workspaceId&&status.sessionId===workbenchIdentity.sessionId
    &&status.project.logicalProjectId===workbenchIdentity.logicalProjectId;
  const changedWorkbench=():ApiFailure=>({ok:false,code:"MONITOR_SESSION_EXPIRED",message:"当前监视会话或工程已变化，请重新打开工作台。"});
  const conflictsWithRecovery=()=>active.has("status")||writing.has("probe")||writing.has("sampling")
    ||["probe.connect","probe.reconnect","probe.release","sampling.start","sampling.pause","sampling.resume","sampling.stop"].some(scope=>active.has(scope as RequestScope));
  const key=(state:MonitorState):string=>{
    const status=state.status;
    return status===null?"":status.workspaceId+"/"+status.sessionId+"/"+status.project.logicalProjectId+"/"+status.sampling.bindingEpoch;
  };
  const targetValid=(includeRun:boolean):(()=>boolean)=>{
    const status=getState().status;
    if(status===null)return()=>getState().status===null;
    const original={workspaceId:status.workspaceId,sessionId:status.sessionId,projectId:status.project.logicalProjectId,
      probeId:status.probe.probeId,bindingEpoch:status.sampling.bindingEpoch,
      groupId:status.sampling.groupId,runId:status.sampling.runId};
    return()=>{
      const latest=getState().status;
      return latest!==null&&latest.workspaceId===original.workspaceId&&latest.sessionId===original.sessionId
        &&latest.project.logicalProjectId===original.projectId&&latest.probe.probeId===original.probeId
        &&latest.sampling.bindingEpoch===original.bindingEpoch
        &&(!includeRun||latest.sampling.groupId===original.groupId&&latest.sampling.runId===original.runId);
    };
  };
  const current=(scope:RequestScope,id:bigint)=>!closed&&!blocked&&active.get(scope)===id;
  const retire=(scope:RequestScope,id:bigint):void=>{
    if(active.get(scope)===id)active.delete(scope);
    if(retries.get(scope)?.requestId===id)retries.delete(scope);
    dispatch({type:"request.retired",scope,requestId:id});
  };
  const start=(scope:RequestScope,unique=false):bigint|null=>{
    if(closed||blocked||unique&&active.has(scope))return null;
    const id=nextId++;active.set(scope,id);retries.delete(scope);
    dispatch({type:"request.started",scope,requestId:id});return id;
  };
  const succeed=(scope:RequestScope,id:bigint,data?:LoadedAction):boolean=>{
    if(!current(scope,id))return false;
    active.delete(scope);
    dispatch(data===undefined?{type:"request.succeeded",scope,requestId:id}:{type:"request.succeeded",scope,requestId:id,data});
    return true;
  };
  const blockAccess=(result:ApiFailure):void=>{
    if(closed||blocked)return;
    dispatch({type:"access.blocked",code:result.code,message:result.message});
    blocked=true;lifecycle++;active.clear();retries.clear();writing.clear();reconciling.clear();
    retireLive();
  };
  const fail=(scope:RequestScope,id:bigint,result:ApiFailure,recovery:RecoveryKind,summary:string,run?:()=>Promise<void>,valid?:()=>boolean):void=>{
    if(!current(scope,id))return;
    if(fatalCode(result.code)){blockAccess(result);return;}
    active.delete(scope);
    if(run!==undefined)retries.set(scope,{requestId:id,recovery,run,...(valid===undefined?{}:{valid})});
    dispatch({type:"request.failed",scope,requestId:id,code:result.code,message:result.message,recovery,summary});
  };
  const read=async<T>(scope:RequestScope,summary:string,invoke:(id:bigint)=>Promise<ApiResult<T>>,
      loaded:(data:T)=>LoadedAction|undefined,valid?:()=>boolean,retryRun?:()=>Promise<void>):Promise<void>=>{
    if(valid!==undefined&&!valid())return;
    const id=start(scope);if(id===null)return;
    let result:ApiResult<T>;
    try{result=await invoke(id);}catch(error){result=unexpected(error);}
    if(!current(scope,id))return;
    if(valid!==undefined&&!valid()){
      if(!result.ok&&fatalCode(result.code))fail(scope,id,result,"none",summary);
      else retire(scope,id);
      return;
    }
    if(!result.ok){fail(scope,id,result,"read-retry",summary,retryRun??(()=>read(scope,summary,invoke,loaded,valid)),valid);return;}
    succeed(scope,id,loaded(result.data));
  };
  const groupPages=async(valid:()=>boolean=()=>true):Promise<ApiResult<readonly WatchGroup[]>>=>{
    const first=await api.groups(undefined);
    if(!first.ok)return first;
    const groups=[...first.data.groups],revision=first.data.revision,seen=new Set<string>();
    let cursor=first.data.nextCursor;
    while(cursor!==null){
      if(!valid())return{ok:false,code:"MONITOR_REQUEST_SUPERSEDED",message:"Groups request superseded"};
      if(seen.has(cursor))return{ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Repeated groups cursor"};
      seen.add(cursor);
      const page=await api.groups(cursor);
      if(!page.ok)return page;
      if(page.data.revision!==revision)return{ok:false,code:"MONITOR_GROUPS_CHANGED",message:"Groups changed during pagination"};
      groups.push(...page.data.groups);cursor=page.data.nextCursor;
    }
    return{ok:true,data:groups};
  };
  const refreshGroups=(internal=false):Promise<void>=>writing.has("groups")&&!internal?Promise.resolve():
    read("groups.list",operationSummary("groups.list"),id=>groupPages(()=>current("groups.list",id)),
      groups=>({type:"groups.loaded",groups}),undefined,()=>refreshGroups());
  const refreshStatus=():Promise<void>=>{
    if(liveBusy())return Promise.resolve();
    const {gapRevision}=getState().transport,startedStateRevision=getState().stateRevision;
    return read("status",operationSummary("status"),async()=>{
      const result=await api.status();
      return result.ok&&!sameWorkbench(result.data)?changedWorkbench():result;
    },
      status=>({type:"status.loaded",status,startedGapRevision:gapRevision,startedStateRevision}),undefined,refreshStatus);
  };
  const refreshProbes=()=>read("probes",operationSummary("probes"),()=>api.probes(),
    data=>({type:"probes.loaded",probes:data.probes}));
  const write=async<T>(scope:RequestScope,family:Family,summary:string,invoke:()=>Promise<ApiResult<T>>,
    accepted:(data:T)=>LoadedAction|undefined,followup:(data:T)=>Promise<void>,reconcile?:()=>Promise<void>,valid?:()=>boolean):Promise<void>=>{
    if(writing.has(family)||liveBusy()&&(family==="probe"||family==="sampling")||valid!==undefined&&!valid())return;
    const startedGeneration=getState().groupGeneration;
    if(family==="groups"){
      const old=active.get("groups.list")??retries.get("groups.list")?.requestId;
      if(old!==undefined)retire("groups.list",old);
    }
    const id=start(scope,true);if(id===null)return;
    writing.add(family);
    if(family==="groups")dispatch({type:"group.write.started"});
    try{
      let result:ApiResult<T>;
      try{result=await invoke();}catch(error){result=unexpected(error);}
      if(!current(scope,id))return;
      if(!result.ok){
        const uncertain=uncertainCode(result.code);
        const conflict=family==="groups"&&groupConflictCode(result.code);
        const input=family==="groups"&&groupInputCode(result.code);
        const recovery:RecoveryKind=conflict?"groups-refresh":input?"input":uncertain?(reconcile===undefined?"none":"reconcile"):"write-confirm";
        const retryRun=conflict?()=>refreshGroups():input?undefined:uncertain?reconcile:()=>write(scope,family,summary,invoke,accepted,followup,reconcile,valid);
        const retryValid=conflict?(()=>getState().groupGeneration===startedGeneration):valid;
        fail(scope,id,result,recovery,summary,retryRun,retryValid);
        return;
      }
      if(succeed(scope,id,accepted(result.data)))await followup(result.data);
    }finally{writing.delete(family);if(family==="groups")dispatch({type:"group.write.ended"});}
  };
  const catalog=async(kind:"variables"|"registers",query:string,cursor:string|undefined,bindingKey:string):Promise<void>=>{
    const scope:RequestScope=kind==="variables"?"catalog.variables":"catalog.registers";
    const summary=operationSummary(scope,query,cursor);
    if(kind==="variables")await read(scope,summary,()=>api.variables(query,cursor),
      data=>({type:"catalog.loaded",catalog:"variables",query,bindingKey,cursor:cursor??null,items:data.items,nextCursor:data.nextCursor}),
      ()=>key(getState())===bindingKey);
    else await read(scope,summary,()=>api.registers(query,cursor),
      data=>({type:"catalog.loaded",catalog:"registers",query,bindingKey,cursor:cursor??null,items:data.items,nextCursor:data.nextCursor}),
      ()=>key(getState())===bindingKey);
  };
  const history=async(queryInput:HistoryQuery,navigation:"replace"|"next"|"previous"):Promise<void>=>{
    const query={...queryInput};
    await read("history",operationSummary("history",String(query.startNs),String(query.endNs),query.cursor),()=>api.history(query),
      page=>({type:"history.loaded",page,query,navigation}));
  };
  const exportStatus=(exportId:string)=>read("export.status",operationSummary("export.status",exportId),
    ()=>api.exportStatus(exportId),artifact=>({type:"export.loaded",artifact}),
    ()=>getState().exports.artifact?.exportId===exportId);
  const download=async(exportId:string):Promise<void>=>{
    const scope:RequestScope="export.download",summary=operationSummary(scope,exportId),id=start(scope);
    if(id===null)return;
    let result:Awaited<ReturnType<MonitorApi["downloadExport"]>>;
    try{result=await api.downloadExport(exportId);}catch(error){result=unexpected(error);}
    if(!current(scope,id))return;
    if(!result.ok){fail(scope,id,result,"read-retry",summary,()=>download(exportId));return;}
    try{
      const url=URL.createObjectURL(result.blob);
      try{const anchor=document.createElement("a");anchor.href=url;anchor.download=result.filename;anchor.click();}
      finally{URL.revokeObjectURL(url);}
      succeed(scope,id);
    }catch(error){fail(scope,id,unexpected(error),"read-retry",summary,()=>download(exportId));}
  };
  const startLiveConnection=(cursor:bigint|null,recoveryId:bigint|null,identity:MonitorStatus):void=>{
    const generation=++liveGeneration;
    if(recoveryId===null)connectingInitial=true;
    dispatch({type:"transport.connecting"});
    const alive=()=>!closed&&!blocked&&generation===liveGeneration;
    const terminal=()=>{
      if(!alive())return;
      retireLive();
      dispatch({type:"transport.stale"});
      if(recoveryId!==null)fail("live.reconnect",recoveryId,
        {ok:false,code:"MONITOR_LIVE_FAILED",message:"Real-time data connection failed"},
        "read-retry",operationSummary("live.reconnect"),reconnectLive);
    };
    try{
      const stop=openLive(window.location.origin,cursor,{
        onOpen:()=>{
          if(!alive())return;
          connectingInitial=false;
          dispatch({type:"transport.open"});
          if(recoveryId!==null)succeed("live.reconnect",recoveryId);
        },
        onEnvelope:value=>{
          if(!alive())return;
          if(value.event.type==="state"){
            const status=value.event.data.status;
            if(status.workspaceId!==identity.workspaceId||status.sessionId!==identity.sessionId
              ||status.project.logicalProjectId!==identity.project.logicalProjectId){
              blockAccess(changedWorkbench());
              return;
            }
          }
          dispatch({type:"live.envelope",value});
        },
        onFailed:terminal,onClosed:terminal,
      });
      if(alive())closeLive=stop;
      else stop();
    }catch{terminal();}
  };
  const reconnectLive=async():Promise<void>=>{
    if(!initialized||closed||blocked||getState().status===null||workbenchIdentity===null||liveBusy()||closeLive!==null||conflictsWithRecovery())return;
    const original=getState().status!;
    const id=start("live.reconnect",true);if(id===null)return;
    retireLive();
    dispatch({type:"transport.checking"});
    let result:ApiResult<MonitorStatus>;
    try{result=await api.status();}catch(error){result=unexpected(error);}
    if(!current("live.reconnect",id))return;
    if(!result.ok){
      fail("live.reconnect",id,result,"read-retry",operationSummary("live.reconnect"),reconnectLive);
      dispatch({type:"transport.stale"});
      return;
    }
    if(!sameWorkbench(result.data)){
      blockAccess(changedWorkbench());
      return;
    }
    startLiveConnection(getState().lastAcceptedEventId,id,original);
  };
  const cancelLiveReconnect=():void=>{
    const id=active.get("live.reconnect");
    if(id===undefined&&!connectingInitial)return;
    retireLive();
    if(id!==undefined)retire("live.reconnect",id);
    dispatch({type:"transport.stale"});
  };
  const initial=async():Promise<void>=>{
    if(initialized)return;
    const id=start("initial",true);if(id===null)return;
    const epoch=lifecycle;
    latestInitialId=id;
    let signalFailure!:(failure:ApiFailure)=>void;
    const firstFailure=new Promise<ApiFailure>(resolve=>{signalFailure=resolve;});
    let signaled=false;
    const latest=()=>!closed&&!blocked&&latestInitialId===id&&epoch===lifecycle;
    const observe=async<T>(invoke:()=>Promise<ApiResult<T>>):Promise<ApiResult<T>>=>{
      let result:ApiResult<T>;
      try{result=await invoke();}catch(error){result=unexpected(error);}
      if(!result.ok&&latest()){
        if(fatalCode(result.code)){
          blockAccess(result);
          if(!signaled){signaled=true;signalFailure(result);}
        }
        else if(!signaled){signaled=true;signalFailure(result);}
      }
      return result;
    };
    const all=Promise.all([
      observe(()=>api.status()),observe(()=>api.probes()),
      observe(()=>groupPages(()=>current("initial",id)&&epoch===lifecycle)),
    ]);
    const outcome=await Promise.race([
      all.then(results=>({kind:"complete" as const,results})),
      firstFailure.then(failure=>({kind:"failed" as const,failure})),
    ]);
    if(outcome.kind==="failed"){
      if(latest())fail("initial",id,outcome.failure,"read-retry",operationSummary("initial"),initial);
      return;
    }
    if(!current("initial",id)||epoch!==lifecycle)return;
    const [status,probes,groups]=outcome.results;
    const failures=[status,probes,groups].filter((result):result is ApiFailure=>!result.ok);
    const failure=failures.find(result=>fatalCode(result.code))??failures[0]??null;
    if(failure!==null){fail("initial",id,failure,"read-retry",operationSummary("initial"),initial);return;}
    if(!status.ok||!probes.ok||!groups.ok)return;
    if(!succeed("initial",id,{type:"initial.loaded",status:status.data,probes:probes.data.probes,groups:groups.data}))return;
    initialized=true;
    workbenchIdentity={workspaceId:status.data.workspaceId,sessionId:status.data.sessionId,logicalProjectId:status.data.project.logicalProjectId};
    if(closed||blocked||epoch!==lifecycle||closeLive!==null)return;
    startLiveConnection(null,null,status.data);
  };
  const noAction=()=>undefined;
  const saveGroup=(draftInput:GroupDraft):Promise<void>=>{
    const state=getState(),draft=cloneDraft(draftInput),generation=state.groupGeneration;
    if(state.groupNavigation!==null||state.groupNameReviewRequired||!sameDraft(draft,state.groupDraft)||
      draft.sourceGroupId!==null&&groupSourceProblem(state)!==null)return Promise.resolve();
    const valid=()=>{
      const latest=getState();
      return latest.groupGeneration===generation&&latest.groupNavigation===null&&!latest.groupNameReviewRequired&&
        sameDraft(latest.groupDraft,draft)&&
        (draft.sourceGroupId===null||groupSourceProblem(latest)===null);
    };
    if(draft.sourceGroupId===null)return write("groups.create","groups",operationSummary("groups.create",draft.name),
      ()=>api.createGroup({authorized:true,name:draft.name,description:draft.description,intervalMs:draft.intervalMs,items:draft.items}),
      group=>({type:"group.acknowledged",group,generation}),()=>refreshGroups(true),()=>refreshGroups(),valid);
    if(draft.expectedRevision===null)return Promise.resolve();
    return write("groups.update","groups",operationSummary("groups.update",draft.name,draft.sourceGroupId),
      ()=>api.updateGroup(draft.sourceGroupId!,{authorized:true,expectedRevision:draft.expectedRevision!,name:draft.name,
        description:draft.description,intervalMs:draft.intervalMs,items:draft.items}),
      group=>({type:"group.acknowledged",group,generation}),()=>refreshGroups(true),()=>refreshGroups(),valid);
  };
  return{
    loadInitial:initial,refreshStatus,reconnectLive,cancelLiveReconnect,refreshProbes,refreshGroups:()=>refreshGroups(),
    connectProbe:probeId=>write("probe.connect","probe",operationSummary("probe.connect",probeId),
      ()=>api.connect(probeId),noAction,refreshStatus,refreshStatus,targetValid(false)),
    reconnectProbe:()=>write("probe.reconnect","probe",operationSummary("probe.reconnect",getState().status?.probe.probeId??undefined),
      ()=>api.reconnect(),noAction,refreshStatus,refreshStatus,targetValid(false)),
    releaseProbe:()=>write("probe.release","probe",operationSummary("probe.release",getState().status?.probe.probeId??undefined),
      ()=>api.release(),noAction,refreshStatus,refreshStatus,targetValid(false)),
    searchCatalog:(kind,query)=>{const bindingKey=key(getState());return bindingKey===""?Promise.resolve():catalog(kind,query,undefined,bindingKey);},
    nextCatalog:kind=>{
      const prior=getState().catalog[kind],bindingKey=key(getState());
      return prior===null||prior.nextCursor===null||prior.bindingKey!==bindingKey
        ?Promise.resolve():catalog(kind,prior.query,prior.nextCursor,bindingKey);
    },
    createGroup:()=>getState().groupDraft.sourceGroupId===null?saveGroup(getState().groupDraft):Promise.resolve(),
    saveGroup,
    deleteGroup:(groupId,expectedRevision,editorGeneration)=>{
      const group=getState().groups.find(item=>item.groupId===groupId);
      if(group===undefined||expectedRevision!==undefined&&group.revision!==expectedRevision||
        editorGeneration!==undefined&&getState().groupGeneration!==editorGeneration||
        getState().groupNavigation!==null)return Promise.resolve();
      const revision=expectedRevision??group.revision,generation=editorGeneration??getState().groupGeneration;
      const valid=()=>getState().groupGeneration===generation&&
        getState().groups.some(item=>item.groupId===groupId&&item.revision===revision);
      return write("groups.delete","groups",operationSummary("groups.delete",group.name,groupId),
        ()=>api.deleteGroup(groupId,{authorized:true,expectedRevision:revision}),
        ()=>({type:"group.deleted",groupId}),()=>refreshGroups(true),()=>refreshGroups(),valid);
    },
    importGroups:value=>{
      if(writing.has("groups"))return Promise.resolve();
      const parsed=parseGroupImport(value);
      if(!parsed.ok){
        const id=start("groups.import",true);
        if(id!==null)fail("groups.import",id,parsed,"input",operationSummary("groups.import"));
        return Promise.resolve();
      }
      const doc=cloneImport(parsed.data);
      return write("groups.import","groups",operationSummary("groups.import",String(doc.groups.length)),
        ()=>api.importGroups(doc),groups=>({type:"groups.imported",groups}),()=>refreshGroups(true),()=>refreshGroups());
    },
    startSampling:(groupId,expectedRevision)=>write("sampling.start","sampling",
      operationSummary("sampling.start",groupId,getState().status?.probe.probeId??undefined,getState().status?.sampling.runId??undefined),
      ()=>api.start(groupId,expectedRevision),noAction,refreshStatus,refreshStatus,targetValid(true)),
    pauseSampling:()=>write("sampling.pause","sampling",
      operationSummary("sampling.pause",getState().status?.sampling.groupId??undefined,getState().status?.sampling.runId??undefined,getState().status?.probe.probeId??undefined),
      ()=>api.pause(),noAction,refreshStatus,refreshStatus,targetValid(true)),
    resumeSampling:()=>write("sampling.resume","sampling",
      operationSummary("sampling.resume",getState().status?.sampling.groupId??undefined,getState().status?.sampling.runId??undefined,getState().status?.probe.probeId??undefined),
      ()=>api.resume(),noAction,refreshStatus,refreshStatus,targetValid(true)),
    stopSampling:()=>write("sampling.stop","sampling",
      operationSummary("sampling.stop",getState().status?.sampling.groupId??undefined,getState().status?.sampling.runId??undefined,getState().status?.probe.probeId??undefined),
      ()=>api.stop(),noAction,refreshStatus,refreshStatus,targetValid(true)),
    loadHistory:query=>history(query,"replace"),
    nextHistory:cursor=>{
      const currentPage=getState().history;
      if(currentPage.query===null)return Promise.resolve();
      const query={...currentPage.query};
      if(cursor===undefined)delete query.cursor;else query.cursor=cursor;
      const top=currentPage.cursorStack.at(-1);
      const navigation=cursor===currentPage.nextCursor&&cursor!==null?"next"
        :currentPage.cursorStack.length>0&&cursor===top?"previous":"replace";
      return history(query,navigation);
    },
    createExport:(startNs,endNs,format)=>{
      const submitted={startNs,endNs,format};
      return write("export.create","export",operationSummary("export.create",format,String(startNs),String(endNs)),
        ()=>api.createExport(startNs,endNs,format),artifact=>({type:"export.loaded",artifact,submitted:{...submitted,exportId:artifact.exportId}}),
        async()=>undefined);
    },
    refreshExport:exportStatus,downloadExport:download,
    retry:async(scope,id)=>{
      const retry=retries.get(scope),failure=getState().failures[scope];
      if(retry===undefined||retry.requestId!==id||failure?.requestId!==id||active.has(scope)||closed||blocked||reconciling.has(scope))return;
      if(retry.valid!==undefined&&!retry.valid()){retire(scope,id);return;}
      if(retry.recovery!=="reconcile"){await retry.run();return;}
      reconciling.add(scope);
      dispatch({type:"request.reconciling",scope,requestId:id});
      try{await retry.run();}
      finally{
        reconciling.delete(scope);
        dispatch({type:"request.reconciled",scope,requestId:id});
      }
    },
    dismiss:(scope,id)=>{
      if(getState().failures[scope]?.requestId!==id)return;
      const retry=retries.get(scope);
      if(retry!==undefined&&retry.requestId!==id)return;
      retries.delete(scope);dispatch({type:"request.dismissed",scope,requestId:id});
    },
    close:()=>{
      if(closed)return;
      closed=true;lifecycle++;active.clear();retries.clear();writing.clear();reconciling.clear();
      retireLive();
    },
  };
}
