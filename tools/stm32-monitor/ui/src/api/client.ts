import {encodeJson} from "./wire";
import {debugFirmwareBindingGuard,deletedGroupGuard,exportArtifactGuard,groupPageGuard,historyPageGuard,monitorStatusGuard,parseEnvelope,pausedGuard,probesGuard,registersGuard,releasedGuard,resumedGuard,samplerStartGuard,stoppedGuard,variablesGuard,watchGroupGuard,watchGroupsGuard,type ApiResult,type DataGuard,type DownloadResult,type GroupImportDocument,type HistoryQuery,type MonitorApi} from "./contract";

type FetchLike=(input:RequestInfo|URL,init?:RequestInit)=>Promise<Response>;
const pathSegment=(value:string)=>encodeURIComponent(value);
export function createMonitorApi(fetchImpl:FetchLike,origin:string):MonitorApi{
  const exactOrigin=new URL(origin).origin;if(exactOrigin!==origin)throw new Error("origin must be exact");
  const url=(path:string)=>new URL(path,origin+"/").href;
  const call=async<T>(method:string,path:string,operation:string,guard:DataGuard<T>,body?:unknown):Promise<ApiResult<T>>=>{
    const mutation=method!=="GET",headers:Record<string,string>={};if(mutation)headers.Origin=origin;if(body!==undefined)headers["Content-Type"]="application/json";
    try{const response=await fetchImpl(url(path),{method,credentials:"same-origin",headers,...(body===undefined?{}:{body:encodeJson(body)})});return parseEnvelope(await response.text(),operation,guard);}catch{return{ok:false,code:"MONITOR_TRANSPORT_FAILED",message:"Monitor request failed"};}
  };
  const query=(pairs:readonly (readonly [string,string|undefined])[])=>{const result=new URLSearchParams();for(const [key,value] of pairs)if(value!==undefined)result.append(key,value);const text=result.toString();return text===""?"":"?"+text;};
  return{
    status:()=>call("GET","api/v1/status","monitor.status",monitorStatusGuard),
    probes:()=>call("GET","api/v1/probes","monitor.probes.list",probesGuard),
    variables:(value,cursor)=>call("GET","api/v1/catalog/variables"+query([["query",value],["limit","100"],["cursor",cursor]]),"monitor.catalog.variables",variablesGuard),
    registers:(value,cursor)=>call("GET","api/v1/catalog/registers"+query([["query",value],["limit","100"],["cursor",cursor]]),"monitor.catalog.registers",registersGuard),
    groups:(cursor)=>call("GET","api/v1/groups"+query([["limit","16"],["cursor",cursor]]),"monitor.groups.list",groupPageGuard),
    createGroup:(request)=>call("POST","api/v1/groups","monitor.groups.create",watchGroupGuard,request),
    updateGroup:(groupId,request)=>call("PATCH",`api/v1/groups/${pathSegment(groupId)}`,"monitor.groups.update",watchGroupGuard,request),
    deleteGroup:(groupId,request)=>call("DELETE",`api/v1/groups/${pathSegment(groupId)}`,"monitor.groups.delete",deletedGroupGuard,request),
    importGroups:(document:GroupImportDocument)=>call("POST","api/v1/groups/import","monitor.groups.import",watchGroupsGuard,{document,authorized:true}),
    connect:(probeId)=>call("POST","api/v1/probe/connect","monitor.probe.connect",debugFirmwareBindingGuard,{probeId}),
    reconnect:()=>call("POST","api/v1/probe/reconnect","monitor.probe.reconnect",debugFirmwareBindingGuard),
    release:()=>call("POST","api/v1/probe/release","monitor.probe.release",releasedGuard),
    start:(groupId,expectedRevision)=>call("POST","api/v1/sampling/start","monitor.sampling.start",samplerStartGuard,{groupId,expectedRevision}),
    pause:()=>call("POST","api/v1/sampling/pause","monitor.sampling.pause",pausedGuard),
    resume:()=>call("POST","api/v1/sampling/resume","monitor.sampling.resume",resumedGuard),
    stop:()=>call("POST","api/v1/sampling/stop","monitor.sampling.stop",stoppedGuard),
    history:(request:HistoryQuery)=>call("GET","api/v1/history"+query([["startNs",request.startNs.toString(10)],["endNs",request.endNs.toString(10)],["limit",request.limit?.toString(10)],["cursor",request.cursor],["runId",request.runId],["groupId",request.groupId],["selectorKind",request.selectorKind],["selector",request.selector]]),"monitor.history.query",historyPageGuard),
    createExport:(startNs,endNs,format)=>call("POST","api/v1/exports","monitor.exports.create",exportArtifactGuard,{startNs,endNs,format,authorized:true}),
    exportStatus:(exportId)=>call("GET",`api/v1/exports/${pathSegment(exportId)}`,"monitor.exports.get",exportArtifactGuard),
    downloadExport:async(exportId):Promise<DownloadResult>=>{try{const response=await fetchImpl(url(`api/v1/exports/${pathSegment(exportId)}/download`),{method:"GET",credentials:"same-origin",headers:{}});if(!response.ok){const failure=parseEnvelope(await response.text(),"monitor.exports.download",()=>{throw new Error("unexpected success envelope");});return failure.ok?{ok:false,code:"MONITOR_DOWNLOAD_INVALID",message:"Download response is invalid"}:failure;}const disposition=response.headers.get("Content-Disposition")??"",match=/filename="([^"]+)"/.exec(disposition);if(match?.[1]===undefined)return{ok:false,code:"MONITOR_DOWNLOAD_INVALID",message:"Download metadata is invalid"};return{ok:true,blob:await response.blob(),filename:match[1],contentType:response.headers.get("Content-Type")??"application/octet-stream"};}catch{return{ok:false,code:"MONITOR_TRANSPORT_FAILED",message:"Monitor request failed"};}}
  };
}
