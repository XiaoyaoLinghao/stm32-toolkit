import {
  groupImportGuard,
  type GroupDraft,
  type GroupImportDocument,
  type HistoryQuery,
  type MonitorApi,
} from "./api/contract";
import {parseLossless} from "./api/wire";
import {openLive} from "./api/live";
import type {MonitorAction,MonitorState,RequestScope} from "./state/model";

export type Controller={
  loadInitial:()=>Promise<void>;
  refreshStatus:()=>Promise<void>;
  refreshProbes:()=>Promise<void>;
  refreshGroups:()=>Promise<void>;
  connectProbe:(probeId:string)=>Promise<void>;
  reconnectProbe:()=>Promise<void>;
  releaseProbe:()=>Promise<void>;
  searchCatalog:(kind:"variables"|"registers",query:string)=>Promise<void>;
  nextCatalog:(kind:"variables"|"registers")=>Promise<void>;
  createGroup:()=>Promise<void>;
  saveGroup:(draft:GroupDraft)=>Promise<void>;
  deleteGroup:(groupId:string)=>Promise<void>;
  importGroups:(value:unknown)=>Promise<void>;
  startSampling:(groupId:string,expectedRevision:bigint)=>Promise<void>;
  pauseSampling:()=>Promise<void>;
  resumeSampling:()=>Promise<void>;
  stopSampling:()=>Promise<void>;
  loadHistory:(query:HistoryQuery)=>Promise<void>;
  nextHistory:(cursor:string|undefined)=>Promise<void>;
  createExport:(startNs:bigint,endNs:bigint,format:"csv"|"jsonl")=>Promise<void>;
  refreshExport:(exportId:string)=>Promise<void>;
  downloadExport:(exportId:string)=>Promise<void>;
  close:()=>void;
};

function parseGroupImport(value:unknown):{ok:true;data:GroupImportDocument}|{ok:false;code:string;message:string}{
  try{return{ok:true,data:groupImportGuard(value)};}
  catch{/* fall through to the in-memory document path */}
  try{
    // GroupPanel hands over an already-validated in-memory document whose
    // numeric fields are plain numbers; re-encode to wire tokens and re-guard.
    return{ok:true,data:groupImportGuard(parseLossless(JSON.stringify(value)))};
  }catch{return{ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import document is invalid"};}
}

function draftTransfer(draft:GroupDraft):{name:string;description:string;intervalMs:number;items:readonly {kind:"variable";expression:string}[]|readonly {kind:"register";registerPath:string}[]}{
  return{name:draft.name,description:draft.description,intervalMs:draft.intervalMs,items:draft.items as never};
}

export function createController(api:MonitorApi,dispatch:(action:MonitorAction)=>void,getState:()=>MonitorState):Controller{
  let requestId=1n;
  const nextRequestId=():bigint=>requestId++;
  const start=(scope:RequestScope):bigint=>{const id=nextRequestId();dispatch({type:"request.started",scope,requestId:id});return id;};
  const clear=(scope:RequestScope,id:bigint):void=>{dispatch({type:"request.cleared",scope,requestId:id});};
  const fail=(scope:RequestScope,id:bigint,code:string,message:string):void=>{dispatch({type:"request.failed",scope,requestId:id,code,message});};

  const catalogKey=(state:MonitorState):string=>{
    const status=state.status;
    if(status===null)return"";
    return `${status.workspaceId}/${status.sessionId}/${status.project.logicalProjectId}/${status.sampling.bindingEpoch}`;
  };

  const refreshGroupsAfterMutation=async():Promise<void>=>{
    const result=await api.groups(undefined);
    if(result.ok)dispatch({type:"groups.loaded",groups:result.data.groups});
  };

  const refreshStatusAfterMutation=async():Promise<void>=>{
    const result=await api.status();
    if(result.ok)dispatch({type:"status.loaded",status:result.data});
  };

  let closeLive:(()=>void)|null=null;

  return{
    loadInitial:async()=>{
      const [status,probes,first]=await Promise.all([api.status(),api.probes(),api.groups(undefined)]);
      if(!status.ok)fail("initial",nextRequestId(),status.code,status.message);
      if(!probes.ok)fail("initial",nextRequestId(),probes.code,probes.message);
      if(!first.ok){fail("initial",nextRequestId(),first.code,first.message);return;}
      const groups=[...first.data.groups];
      let cursor=first.data.nextCursor;
      while(cursor!==null){
        const page=await api.groups(cursor);
        if(!page.ok){fail("initial",nextRequestId(),page.code,page.message);break;}
        groups.push(...page.data.groups);cursor=page.data.nextCursor;
      }
      if(status.ok&&probes.ok)dispatch({type:"initial.loaded",status:status.data,probes:probes.data.probes,groups});
      if(closeLive!==null){closeLive();closeLive=null;}
      closeLive=openLive(window.location.origin,null,{
        onEnvelope:(value)=>dispatch({type:"live.envelope",value}),
        onClosed:()=>dispatch({type:"transport.stale"}),
      });
      dispatch({type:"transport.open"});
    },
    refreshStatus:async()=>{
      const id=start("status");
      const result=await api.status();
      if(result.ok){clear("status",id);dispatch({type:"status.loaded",status:result.data});}
      else fail("status",id,result.code,result.message);
    },
    refreshProbes:async()=>{
      const id=start("probes");
      const result=await api.probes();
      if(result.ok){clear("probes",id);dispatch({type:"probes.loaded",probes:result.data.probes});}
      else fail("probes",id,result.code,result.message);
    },
    refreshGroups:async()=>{
      const id=start("groups.create");
      const result=await api.groups(undefined);
      if(result.ok){clear("groups.create",id);dispatch({type:"groups.loaded",groups:result.data.groups});}
      else fail("groups.create",id,result.code,result.message);
    },
    connectProbe:async(probeId)=>{
      const id=start("probe.connect");
      const result=await api.connect(probeId);
      if(result.ok){clear("probe.connect",id);await refreshStatusAfterMutation();}
      else fail("probe.connect",id,result.code,result.message);
    },
    reconnectProbe:async()=>{
      const id=start("probe.reconnect");
      const result=await api.reconnect();
      if(result.ok){clear("probe.reconnect",id);await refreshStatusAfterMutation();}
      else fail("probe.reconnect",id,result.code,result.message);
    },
    releaseProbe:async()=>{
      const id=start("probe.release");
      const result=await api.release();
      if(result.ok){clear("probe.release",id);await refreshStatusAfterMutation();}
      else fail("probe.release",id,result.code,result.message);
    },
    searchCatalog:async(kind,query)=>{
      const state=getState();
      if(state.status===null)return;
      const bindingKey=catalogKey(state);
      dispatch({type:"catalog.requested",catalog:kind,query,bindingKey,cursor:null});
      const id=start(kind==="variables"?"catalog.variables":"catalog.registers");
      if(kind==="variables"){
        const result=await api.variables(query);
        if(result.ok){clear("catalog.variables",id);dispatch({type:"catalog.loaded",catalog:"variables",query,bindingKey,cursor:null,items:result.data.items,nextCursor:result.data.nextCursor});}
        else fail("catalog.variables",id,result.code,result.message);
      }else{
        const result=await api.registers(query);
        if(result.ok){clear("catalog.registers",id);dispatch({type:"catalog.loaded",catalog:"registers",query,bindingKey,cursor:null,items:result.data.items,nextCursor:result.data.nextCursor});}
        else fail("catalog.registers",id,result.code,result.message);
      }
    },
    nextCatalog:async(kind)=>{
      const state=getState();
      const prior=kind==="variables"?state.catalog.variables:state.catalog.registers;
      if(prior===null||prior.nextCursor===null)return;
      const query=prior.query,bindingKey=prior.bindingKey,cursor:string|undefined=prior.nextCursor;
      dispatch({type:"catalog.requested",catalog:kind,query,bindingKey,cursor});
      const id=start(kind==="variables"?"catalog.variables":"catalog.registers");
      if(kind==="variables"){
        const result=await api.variables(query,cursor);
        if(result.ok){clear("catalog.variables",id);dispatch({type:"catalog.loaded",catalog:"variables",query,bindingKey,cursor,items:result.data.items,nextCursor:result.data.nextCursor});}
        else fail("catalog.variables",id,result.code,result.message);
      }else{
        const result=await api.registers(query,cursor);
        if(result.ok){clear("catalog.registers",id);dispatch({type:"catalog.loaded",catalog:"registers",query,bindingKey,cursor,items:result.data.items,nextCursor:result.data.nextCursor});}
        else fail("catalog.registers",id,result.code,result.message);
      }
    },
    createGroup:async()=>{
      const draft=getState().groupDraft;
      if(draft.sourceGroupId!==null)return;
      const id=start("groups.create");
      const result=await api.createGroup({authorized:true,...draftTransfer(draft)});
      if(result.ok){clear("groups.create",id);await refreshGroupsAfterMutation();}
      else fail("groups.create",id,result.code,result.message);
    },
    saveGroup:async(draft)=>{
      if(draft.sourceGroupId===null){
        const id=start("groups.create");
        const result=await api.createGroup({authorized:true,...draftTransfer(draft)});
        if(result.ok){clear("groups.create",id);await refreshGroupsAfterMutation();}
        else fail("groups.create",id,result.code,result.message);
        return;
      }
      if(draft.expectedRevision===null)return;
      const id=start("groups.update");
      const result=await api.updateGroup(draft.sourceGroupId,{authorized:true,expectedRevision:draft.expectedRevision,name:draft.name,description:draft.description,intervalMs:draft.intervalMs,items:draft.items});
      if(result.ok){clear("groups.update",id);await refreshGroupsAfterMutation();}
      else fail("groups.update",id,result.code,result.message);
    },
    deleteGroup:async(groupId)=>{
      const group=getState().groups.find(item=>item.groupId===groupId);
      if(group===undefined)return;
      const id=start("groups.delete");
      const result=await api.deleteGroup(groupId,{authorized:true,expectedRevision:group.revision});
      if(result.ok){clear("groups.delete",id);await refreshGroupsAfterMutation();}
      else fail("groups.delete",id,result.code,result.message);
    },
    importGroups:async(value)=>{
      const parsed=parseGroupImport(value);
      if(!parsed.ok){fail("groups.import",nextRequestId(),parsed.code,parsed.message);return;}
      const id=start("groups.import");
      const result=await api.importGroups(parsed.data);
      if(result.ok){clear("groups.import",id);await refreshGroupsAfterMutation();}
      else fail("groups.import",id,result.code,result.message);
    },
    startSampling:async(groupId,expectedRevision)=>{
      const id=start("sampling.start");
      const result=await api.start(groupId,expectedRevision);
      if(result.ok){clear("sampling.start",id);await refreshStatusAfterMutation();}
      else fail("sampling.start",id,result.code,result.message);
    },
    pauseSampling:async()=>{
      const id=start("sampling.pause");
      const result=await api.pause();
      if(result.ok){clear("sampling.pause",id);await refreshStatusAfterMutation();}
      else fail("sampling.pause",id,result.code,result.message);
    },
    resumeSampling:async()=>{
      const id=start("sampling.resume");
      const result=await api.resume();
      if(result.ok){clear("sampling.resume",id);await refreshStatusAfterMutation();}
      else fail("sampling.resume",id,result.code,result.message);
    },
    stopSampling:async()=>{
      const id=start("sampling.stop");
      const result=await api.stop();
      if(result.ok){clear("sampling.stop",id);await refreshStatusAfterMutation();}
      else fail("sampling.stop",id,result.code,result.message);
    },
    loadHistory:async(query)=>{
      const id=start("history");
      const result=await api.history(query);
      if(result.ok){clear("history",id);dispatch({type:"history.loaded",page:result.data,query});}
      else fail("history",id,result.code,result.message);
    },
    nextHistory:async(cursor)=>{
      const current=getState().history.query;
      if(current===null)return;
      const nextQuery:HistoryQuery={startNs:current.startNs,endNs:current.endNs};
      if(current.limit!==undefined)nextQuery.limit=current.limit;
      if(current.runId!==undefined)nextQuery.runId=current.runId;
      if(current.groupId!==undefined)nextQuery.groupId=current.groupId;
      if(current.selectorKind!==undefined)nextQuery.selectorKind=current.selectorKind;
      if(current.selector!==undefined)nextQuery.selector=current.selector;
      if(cursor!==undefined)nextQuery.cursor=cursor;
      const id=start("history");
      const result=await api.history(nextQuery);
      if(result.ok){clear("history",id);dispatch({type:"history.loaded",page:result.data,query:nextQuery});}
      else fail("history",id,result.code,result.message);
    },
    createExport:async(startNs,endNs,format)=>{
      const id=start("export.create");
      const result=await api.createExport(startNs,endNs,format);
      if(result.ok){clear("export.create",id);dispatch({type:"export.loaded",artifact:result.data});}
      else fail("export.create",id,result.code,result.message);
    },
    refreshExport:async(exportId)=>{
      const id=start("export.status");
      const result=await api.exportStatus(exportId);
      if(result.ok){clear("export.status",id);dispatch({type:"export.loaded",artifact:result.data});}
      else fail("export.status",id,result.code,result.message);
    },
    downloadExport:async(exportId)=>{
      const result=await api.downloadExport(exportId);
      if(!result.ok){fail("export.download",nextRequestId(),result.code,result.message);return;}
      const url=URL.createObjectURL(result.blob);
      const anchor=document.createElement("a");
      anchor.href=url;anchor.download=result.filename;anchor.click();
      URL.revokeObjectURL(url);
    },
    close:()=>{if(closeLive!==null){closeLive();closeLive=null;}},
  };
}
