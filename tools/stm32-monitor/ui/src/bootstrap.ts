import {authenticatedGuard,parseEnvelopeText,type ApiResult} from "./api/contract";

const STARTUP_ERRORS={
  MONITOR_ACCESS_LINK_INVALID:"Monitor access link is missing or invalid. Return to the Monitor terminal and run open to create a new authenticated tab.",
  MONITOR_ACCESS_REJECTED:"Monitor rejected this access link. Check the Monitor terminal, then run open to create a new authenticated tab.",
  MONITOR_BOOTSTRAP_SERVICE_FAILED:"Monitor could not start. Check the Monitor terminal, then run open to create a new authenticated tab.",
  MONITOR_BOOTSTRAP_RESPONSE_INVALID:"Monitor returned an invalid startup response. Check the Monitor terminal, then run open to create a new authenticated tab.",
  MONITOR_BOOTSTRAP_REQUEST_FAILED:"Monitor startup request did not complete. Check the Monitor terminal, then run open to create a new authenticated tab.",
} as const;
type StartupErrorCode=keyof typeof STARTUP_ERRORS;
const startupFailure=(code:StartupErrorCode):ApiResult<{authenticated:true}>=>({ok:false,code,message:STARTUP_ERRORS[code]});

export function takeFragmentToken(windowLike:Pick<Window,"location"|"history">):string|null{
  const raw=windowLike.location.hash.startsWith("#")?windowLike.location.hash.slice(1):"";
  windowLike.history.replaceState(null,"","/");
  const params=new URLSearchParams(raw);
  const values=params.getAll("token");
  return windowLike.location.search===""&&[...params.keys()].every(k=>k==="token")&&values.length===1&&
    /^[0-9a-f]{64}$/.test(values[0]!) ? values[0]! : null;
}

export async function bootstrapFromFragment(windowLike:Window,fetchLike:typeof fetch):Promise<ApiResult<{authenticated:true}>>{
  let token:string|null=takeFragmentToken(windowLike);
  if(token===null)return startupFailure("MONITOR_ACCESS_LINK_INVALID");
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
}

export function renderStartupError(documentLike:Document,code:string):void{
  const host=documentLike.getElementById("app")??documentLike.body;
  const alert=documentLike.createElement("p");
  alert.setAttribute("role","alert");
  alert.textContent=Object.prototype.hasOwnProperty.call(STARTUP_ERRORS,code)
    ?STARTUP_ERRORS[code as StartupErrorCode]
    :"Monitor could not start. Check the Monitor terminal and run open to create a new authenticated tab.";
  host.replaceChildren(alert);
}
