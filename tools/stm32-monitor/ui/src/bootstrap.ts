import {authenticatedGuard,monitorStatusGuard,parseEnvelopeText,type ApiResult} from "./api/contract";
import {copy,errorText} from "./presentation/zh";

type StartupErrorCode=
  "MONITOR_ACCESS_LINK_INVALID"|"MONITOR_ACCESS_REJECTED"|"MONITOR_BOOTSTRAP_SERVICE_FAILED"|
  "MONITOR_BOOTSTRAP_RESPONSE_INVALID"|"MONITOR_BOOTSTRAP_REQUEST_FAILED"|"MONITOR_SESSION_EXPIRED";
const startupCopy=(code:string)=>[
  "MONITOR_SESSION_EXPIRED","MONITOR_ACCESS_REJECTED","MONITOR_ACCESS_LINK_INVALID",
].includes(code)?errorText(code).action:copy.retryOpen;
const startupFailure=(code:StartupErrorCode):ApiResult<{authenticated:true}>=>({ok:false,code,message:`${errorText(code).title}。${startupCopy(code)}`});

type Entry={kind:"plain"}|{kind:"token";token:string}|{kind:"invalid"};
function classifyEntry(windowLike:Pick<Window,"location"|"history">):Entry{
  const {href,origin,pathname,search,hash}=windowLike.location;
  const root=origin+"/";
  if(href===root&&pathname==="/"&&search===""&&hash==="")return{kind:"plain"};
  const fragmentAt=href.indexOf("#");
  if(pathname!=="/"||search!==""||fragmentAt<0||href.slice(0,fragmentAt)!==root)return{kind:"invalid"};
  const raw=hash.startsWith("#")?hash.slice(1):"";
  const params=new URLSearchParams(raw);
  const values=params.getAll("token");
  return [...params.keys()].every(k=>k==="token")&&values.length===1&&
    /^[0-9a-f]{64}$/.test(values[0]!)?{kind:"token",token:values[0]!}:{kind:"invalid"};
}

function takeEntry(windowLike:Pick<Window,"location"|"history">):Entry{
  const entry=classifyEntry(windowLike);
  if(entry.kind!=="plain")windowLike.history.replaceState(null,"","/");
  return entry;
}

export function takeFragmentToken(windowLike:Pick<Window,"location"|"history">):string|null{
  const entry=takeEntry(windowLike);
  return entry.kind==="token"?entry.token:null;
}

export function createStartupSession(windowLike:Window,fetchLike:typeof fetch):{
  canRecheckSession:boolean;
  check:()=>Promise<ApiResult<{authenticated:true}>>;
}{
  // Keep the entry classification from before URL scrubbing. A rejected fragment
  // must never become a plain-root cookie request on a later click.
  let entry=takeEntry(windowLike);
  const canRecheckSession=entry.kind==="plain";
  return{canRecheckSession,check:async()=>{
    if(entry.kind==="plain"){
      try{
        const response=await fetchLike("/api/v1/status",{method:"GET",credentials:"same-origin"});
        if(!response.ok)return startupFailure(response.status===401?"MONITOR_SESSION_EXPIRED":
          response.status===403?"MONITOR_ACCESS_REJECTED":"MONITOR_BOOTSTRAP_SERVICE_FAILED");
        const result=parseEnvelopeText(await response.text(),"monitor.status",monitorStatusGuard);
        return result.ok?{ok:true,data:{authenticated:true}}:startupFailure(result.code==="MONITOR_RESPONSE_INVALID"
          ?"MONITOR_BOOTSTRAP_RESPONSE_INVALID":"MONITOR_BOOTSTRAP_SERVICE_FAILED");
      }catch{
        return startupFailure("MONITOR_BOOTSTRAP_REQUEST_FAILED");
      }
    }
    if(entry.kind==="invalid")return startupFailure("MONITOR_ACCESS_LINK_INVALID");
    let token:string|null=entry.token;
    entry={kind:"invalid"};
    try{
      const response=await fetchLike("/api/v1/auth/bootstrap",{method:"POST",credentials:"same-origin",
        headers:new Headers({Authorization:`Bearer ${token}`}),body:null});
      if(!response.ok)return startupFailure(response.status===401||response.status===403
        ?"MONITOR_ACCESS_REJECTED":"MONITOR_BOOTSTRAP_SERVICE_FAILED");
      const result=parseEnvelopeText(await response.text(),"monitor.auth.bootstrap",authenticatedGuard);
      if(!result.ok)return startupFailure(result.code==="MONITOR_RESPONSE_INVALID"
        ?"MONITOR_BOOTSTRAP_RESPONSE_INVALID":"MONITOR_ACCESS_REJECTED");
      return result;
    }catch{
      return startupFailure("MONITOR_BOOTSTRAP_REQUEST_FAILED");
    }finally{
      token=null;
    }
  }};
}

export function bootstrapFromFragment(windowLike:Window,fetchLike:typeof fetch):Promise<ApiResult<{authenticated:true}>>{
  return createStartupSession(windowLike,fetchLike).check();
}

export function renderStartupError(documentLike:Document,code:string,onRecheck?:()=>Promise<void>):void{
  const host=documentLike.getElementById("app")??documentLike.body;
  const alert=documentLike.createElement("p");
  alert.className="startup-alert";
  alert.setAttribute("role","alert");
  alert.textContent=`${errorText(code).title}。${startupCopy(code)}`;
  host.replaceChildren(alert);
  if(code==="MONITOR_SESSION_EXPIRED"&&onRecheck){
    const button=documentLike.createElement("button");
    button.type="button";
    button.className="startup-retry";
    button.dataset.startupRetry="";
    button.textContent=copy.recheckSession;
    button.addEventListener("click",()=>{
      if(button.disabled)return;
      button.disabled=true;
      void onRecheck();
    });
    host.append(button);
  }
}
