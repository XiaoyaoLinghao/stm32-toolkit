import {authenticatedGuard,parseEnvelopeText,type ApiResult} from "./api/contract";

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
  if(token===null)return{ok:false,code:"MONITOR_BOOTSTRAP_FAILED",message:"Monitor could not start"};
  try{
    const response=await fetchLike("/api/v1/auth/bootstrap",{method:"POST",credentials:"same-origin",
      headers:new Headers({Authorization:`Bearer ${token}`}),body:null});
    return parseEnvelopeText(await response.text(),"monitor.auth.bootstrap",authenticatedGuard);
  }catch{
    return{ok:false,code:"MONITOR_BOOTSTRAP_FAILED",message:"Monitor could not start"};
  }finally{
    token=null;
  }
}

export function renderStartupError(documentLike:Document):void{
  const host=documentLike.getElementById("app")??documentLike.body;
  const alert=documentLike.createElement("p");
  alert.setAttribute("role","alert");
  alert.textContent="Monitor could not start";
  host.replaceChildren(alert);
}
