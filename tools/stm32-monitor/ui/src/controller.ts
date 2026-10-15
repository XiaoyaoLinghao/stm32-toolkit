import {
  groupImportGuard,
  type ApiFailure,type ApiResult,type GroupDraft,type GroupImportDocument,
  type HistoryQuery,type MonitorApi,type WatchGroup,type WatchItem,
} from "./api/contract";
import {parseLossless} from "./api/wire";
import {openLive} from "./api/live";
import {operationSummary} from "./presentation/zh";
import type {LoadedAction,MonitorAction,MonitorState,RecoveryKind,RequestScope} from "./state/model";

export type Controller={
  loadInitial:()=>Promise<void>;refreshStatus:()=>Promise<void>;refreshProbes:()=>Promise<void>;refreshGroups:()=>Promise<void>;
  connectProbe:(probeId:string)=>Promise<void>;reconnectProbe:()=>Promise<void>;releaseProbe:()=>Promise<void>;
  searchCatalog:(kind:"variables"|"registers",query:string)=>Promise<void>;
  nextCatalog:(kind:"variables"|"registers")=>Promise<void>;
  createGroup:()=>Promise<void>;saveGroup:(draft:GroupDraft)=>Promise<void>;deleteGroup:(groupId:string)=>Promise<void>;
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
const cloneImport=(doc:GroupImportDocument):GroupImportDocument=>({schemaVersion:1,
  groups:doc.groups.map(group=>({...group,items:group.items.map(cloneWatch)}))});
const unexpected=(error:unknown):ApiFailure=>({ok:false,code:"MONITOR_TRANSPORT_FAILED",
  message:error instanceof Error?error.message:String(error)});
const fatalCode=(code:string)=>[
  "MONITOR_AUTH_REQUIRED","MONITOR_PEER_REJECTED","MONITOR_HOST_REJECTED",
  "MONITOR_ORIGIN_REJECTED","MONITOR_SESSION_EXPIRED","MONITOR_ACCESS_REJECTED",
].includes(code);
const uncertainCode=(code:string)=>code==="MONITOR_TRANSPORT_FAILED"||code==="MONITOR_RESPONSE_INVALID";
function parseGroupImport(value:unknown):ApiResult<GroupImportDocument>{
  try{return{ok:true,data:groupImportGuard(value)};}catch{/* In-memory document path. */}
  try{return{ok:true,data:groupImportGuard(parseLossless(JSON.stringify(value)))};}
  catch{return{ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import document is invalid"};}
}
type Retry={requestId:bigint;recovery:RecoveryKind;run:()=>Promise<void>};
type Family="groups"|"probe"|"sampling"|"export";

export function createController(api:MonitorApi,dispatch:(action:MonitorAction)=>void,getState:()=>MonitorState):Controller{
  let nextId=1n,closed=false,blocked=false,initialized=false,lifecycle=0;
  let closeLive:(()=>void)|null=null;
  const active=new Map<RequestScope,bigint>();
  const retries=new Map<RequestScope,Retry>();
  const writing=new Set<Family>();
  const reconciling=new Set<RequestScope>();
  const key=(state:MonitorState):string=>{
    const status=state.status;
    return status===null?"":status.workspaceId+"/"+status.sessionId+"/"+status.project.logicalProjectId+"/"+status.sampling.bindingEpoch;
  };
  const current=(scope:RequestScope,id:bigint)=>!closed&&!blocked&&active.get(scope)===id;
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
  const fail=(scope:RequestScope,id:bigint,result:ApiFailure,recovery:RecoveryKind,summary:string,run?:()=>Promise<void>):void=>{
    if(!current(scope,id))return;
    if(fatalCode(result.code)){
      dispatch({type:"request.failed",scope,requestId:id,code:result.code,message:result.message,fatal:true});
      blocked=true;lifecycle++;active.clear();retries.clear();writing.clear();reconciling.clear();
      if(closeLive!==null){closeLive();closeLive=null;}return;
    }
    active.delete(scope);
    if(run!==undefined)retries.set(scope,{requestId:id,recovery,run});
    dispatch({type:"request.failed",scope,requestId:id,code:result.code,message:result.message,recovery,summary});
  };
  const read=async<T>(scope:RequestScope,summary:string,invoke:(id:bigint)=>Promise<ApiResult<T>>,
      loaded:(data:T)=>LoadedAction|undefined,valid?:()=>boolean):Promise<void>=>{
    if(valid!==undefined&&!valid())return;
    const id=start(scope);if(id===null)return;
    let result:ApiResult<T>;
    try{result=await invoke(id);}catch(error){result=unexpected(error);}
    if(!current(scope,id))return;
    if(!result.ok){fail(scope,id,result,"read-retry",summary,()=>read(scope,summary,invoke,loaded,valid));return;}
    succeed(scope,id,valid===undefined||valid()?loaded(result.data):undefined);
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
  const refreshGroups=(submittedDraft?:GroupDraft,createdGroupId?:string)=>read("groups.list",operationSummary("groups.list"),
    id=>groupPages(()=>current("groups.list",id)),
    groups=>({type:"groups.loaded",groups,...(submittedDraft===undefined?{}:{submittedDraft}),
      ...(createdGroupId===undefined?{}:{createdGroupId})}));
  const refreshStatus=()=>read("status",operationSummary("status"),()=>api.status(),
    status=>({type:"status.loaded",status}));
  const refreshProbes=()=>read("probes",operationSummary("probes"),()=>api.probes(),
    data=>({type:"probes.loaded",probes:data.probes}));
  const write=async<T>(scope:RequestScope,family:Family,summary:string,invoke:()=>Promise<ApiResult<T>>,
    accepted:(data:T)=>LoadedAction|undefined,followup:(data:T)=>Promise<void>,reconcile?:()=>Promise<void>):Promise<void>=>{
    if(writing.has(family))return;
    const id=start(scope,true);if(id===null)return;
    writing.add(family);
    try{
      let result:ApiResult<T>;
      try{result=await invoke();}catch(error){result=unexpected(error);}
      if(!current(scope,id))return;
      if(!result.ok){
        const uncertain=uncertainCode(result.code);
        const recovery:RecoveryKind=uncertain?(reconcile===undefined?"none":"reconcile"):"write-confirm";
        fail(scope,id,result,recovery,summary,uncertain?reconcile:()=>write(scope,family,summary,invoke,accepted,followup,reconcile));
        return;
      }
      if(succeed(scope,id,accepted(result.data)))await followup(result.data);
    }finally{writing.delete(family);}
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
  const initial=async():Promise<void>=>{
    if(initialized)return;
    const id=start("initial",true);if(id===null)return;
    const epoch=lifecycle;
    let status:Awaited<ReturnType<MonitorApi["status"]>>;
    let probes:Awaited<ReturnType<MonitorApi["probes"]>>;
    let groups:Awaited<ReturnType<typeof groupPages>>;
    const observeFatal=async<T>(promise:Promise<ApiResult<T>>):Promise<ApiResult<T>>=>{
      const result=await promise;
      if(!result.ok&&fatalCode(result.code))fail("initial",id,result,"none",operationSummary("initial"));
      return result;
    };
    try{[status,probes,groups]=await Promise.all([
      observeFatal(api.status()),observeFatal(api.probes()),
      observeFatal(groupPages(()=>current("initial",id)&&epoch===lifecycle)),
    ]);}
    catch(error){fail("initial",id,unexpected(error),"read-retry",operationSummary("initial"),initial);return;}
    if(!current("initial",id)||epoch!==lifecycle)return;
    const failures=[status,probes,groups].filter((result):result is ApiFailure=>!result.ok);
    const failure=failures.find(result=>fatalCode(result.code))??failures[0]??null;
    if(failure!==null){fail("initial",id,failure,"read-retry",operationSummary("initial"),initial);return;}
    if(!status.ok||!probes.ok||!groups.ok)return;
    if(!succeed("initial",id,{type:"initial.loaded",status:status.data,probes:probes.data.probes,groups:groups.data}))return;
    initialized=true;
    if(closed||blocked||epoch!==lifecycle||closeLive!==null)return;
    closeLive=openLive(window.location.origin,null,{
      onEnvelope:value=>{if(!closed&&!blocked&&epoch===lifecycle)dispatch({type:"live.envelope",value});},
      onClosed:()=>{if(!closed&&!blocked&&epoch===lifecycle)dispatch({type:"transport.stale"});},
    });
    if(!closed&&!blocked&&epoch===lifecycle)dispatch({type:"transport.open"});
  };
  const noAction=()=>undefined;
  return{
    loadInitial:initial,refreshStatus,refreshProbes,refreshGroups:()=>refreshGroups(),
    connectProbe:probeId=>write("probe.connect","probe",operationSummary("probe.connect",probeId),
      ()=>api.connect(probeId),noAction,refreshStatus,refreshStatus),
    reconnectProbe:()=>write("probe.reconnect","probe",operationSummary("probe.reconnect"),
      ()=>api.reconnect(),noAction,refreshStatus,refreshStatus),
    releaseProbe:()=>write("probe.release","probe",operationSummary("probe.release"),
      ()=>api.release(),noAction,refreshStatus,refreshStatus),
    searchCatalog:(kind,query)=>{const bindingKey=key(getState());return bindingKey===""?Promise.resolve():catalog(kind,query,undefined,bindingKey);},
    nextCatalog:kind=>{
      const prior=getState().catalog[kind],bindingKey=key(getState());
      return prior===null||prior.nextCursor===null||prior.bindingKey!==bindingKey
        ?Promise.resolve():catalog(kind,prior.query,prior.nextCursor,bindingKey);
    },
    createGroup:()=>{
      const draft=cloneDraft(getState().groupDraft);
      return draft.sourceGroupId!==null?Promise.resolve():write("groups.create","groups",operationSummary("groups.create",draft.name),
        ()=>api.createGroup({authorized:true,name:draft.name,description:draft.description,intervalMs:draft.intervalMs,items:draft.items}),
        group=>({type:"group.acknowledged",group,submittedDraft:draft}),group=>refreshGroups(draft,group.groupId),()=>refreshGroups());
    },
    saveGroup:draftInput=>{
      const draft=cloneDraft(draftInput);
      if(draft.sourceGroupId===null)return write("groups.create","groups",operationSummary("groups.create",draft.name),
        ()=>api.createGroup({authorized:true,name:draft.name,description:draft.description,intervalMs:draft.intervalMs,items:draft.items}),
        group=>({type:"group.acknowledged",group,submittedDraft:draft}),group=>refreshGroups(draft,group.groupId),()=>refreshGroups());
      if(draft.expectedRevision===null)return Promise.resolve();
      return write("groups.update","groups",operationSummary("groups.update",draft.name,draft.sourceGroupId),
        ()=>api.updateGroup(draft.sourceGroupId!,{authorized:true,expectedRevision:draft.expectedRevision!,name:draft.name,
          description:draft.description,intervalMs:draft.intervalMs,items:draft.items}),
        group=>({type:"group.acknowledged",group,submittedDraft:draft}),()=>refreshGroups(draft),()=>refreshGroups());
    },
    deleteGroup:groupId=>{
      const group=getState().groups.find(item=>item.groupId===groupId);
      if(group===undefined)return Promise.resolve();
      const revision=group.revision;
      return write("groups.delete","groups",operationSummary("groups.delete",group.name,groupId),
        ()=>api.deleteGroup(groupId,{authorized:true,expectedRevision:revision}),
        noAction,()=>refreshGroups(),()=>refreshGroups());
    },
    importGroups:value=>{
      const parsed=parseGroupImport(value);
      if(!parsed.ok){
        const id=start("groups.import",true);
        if(id!==null)fail("groups.import",id,parsed,"input",operationSummary("groups.import"));
        return Promise.resolve();
      }
      const doc=cloneImport(parsed.data);
      return write("groups.import","groups",operationSummary("groups.import",String(doc.groups.length)),
        ()=>api.importGroups(doc),noAction,()=>refreshGroups(),()=>refreshGroups());
    },
    startSampling:(groupId,expectedRevision)=>write("sampling.start","sampling",operationSummary("sampling.start",groupId),
      ()=>api.start(groupId,expectedRevision),noAction,refreshStatus,refreshStatus),
    pauseSampling:()=>write("sampling.pause","sampling",operationSummary("sampling.pause"),
      ()=>api.pause(),noAction,refreshStatus,refreshStatus),
    resumeSampling:()=>write("sampling.resume","sampling",operationSummary("sampling.resume"),
      ()=>api.resume(),noAction,refreshStatus,refreshStatus),
    stopSampling:()=>write("sampling.stop","sampling",operationSummary("sampling.stop"),
      ()=>api.stop(),noAction,refreshStatus,refreshStatus),
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
      if(closeLive!==null){closeLive();closeLive=null;}
    },
  };
}
