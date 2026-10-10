import {expect,it,vi} from "vitest";
import {bootstrapFromFragment,renderStartupError,takeFragmentToken} from "../src/bootstrap";

const TOKEN="a".repeat(64);

it("scrubs the only valid fragment before bearer bootstrap",async()=>{
  const order:string[]=[];
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  const replace=vi.spyOn(window.history,"replaceState").mockImplementation((...args)=>{
    order.push("scrub");History.prototype.replaceState.apply(window.history,args);});
  const fetchLike=vi.fn(async(_url,init)=>{
    order.push("fetch");
    expect(window.location.hash).toBe("");
    expect(new Headers(init?.headers).get("Authorization")).toBe(`Bearer ${TOKEN}`);
    expect(new Headers(init?.headers).has("Origin")).toBe(false);
    expect(init).toMatchObject({method:"POST",credentials:"same-origin",body:null});
    return new Response(JSON.stringify({protocol:"stm32-toolkit-monitor/1",toolkitVersion:"1.0.0",
      monitorVersion:"1.0.0",ok:true,operation:"monitor.auth.bootstrap",code:"OK",message:"",
      data:{authenticated:true},details:{}}));});
  const result=await bootstrapFromFragment(window,fetchLike);
  expect(order).toEqual(["scrub","fetch"]);
  expect(result).toEqual({ok:true,data:{authenticated:true}});
  expect(window.location.href).not.toContain(TOKEN);
  replace.mockRestore();
});

it.each(["","#token=A"+"a".repeat(63),`#token=${TOKEN}&token=${TOKEN}`,
  "#access_token="+TOKEN,"#token="+TOKEN+"&extra=1"])("rejects fragment %s without fetch",async hash=>{
  window.history.replaceState(null,"",`/${hash}`);
  const fetchLike=vi.fn();
  const result=await bootstrapFromFragment(window,fetchLike);
  expect(result).toMatchObject({ok:false,code:"MONITOR_ACCESS_LINK_INVALID"});
  expect(window.location.hash).toBe("");
  expect(fetchLike).not.toHaveBeenCalled();
});

it("ignores a query token and creates no normal state or request",async()=>{
  window.history.replaceState(null,"",`/?token=${TOKEN}`);
  const fetchLike=vi.fn(),mount=vi.fn();
  const result=await bootstrapFromFragment(window,fetchLike);
  if(result.ok)mount(result.data);
  expect(result.ok).toBe(false);
  expect(fetchLike).not.toHaveBeenCalled();
  expect(mount).not.toHaveBeenCalled();
});

it("returns only fixed startup copy on an incomplete bootstrap request",async()=>{
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  const result=await bootstrapFromFragment(window,vi.fn().mockRejectedValue(new Error(TOKEN)));
  expect(result).toMatchObject({ok:false,code:"MONITOR_BOOTSTRAP_REQUEST_FAILED"});
  expect(JSON.stringify(result)).not.toContain(TOKEN);
  renderStartupError(document,result.ok?"":result.code);
  expect(document.querySelector('[role="alert"]')?.textContent).toContain("request did not complete");
  expect(document.body.textContent).not.toContain(TOKEN);
});

it("renders fixed recovery for a valid rejected bootstrap envelope without exposing private fields",async()=>{
  const privateMessage="private rejection message";
  const privateDetail="private diagnostic detail";
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  const response=new Response(JSON.stringify({
    protocol:"stm32-toolkit-monitor/1",toolkitVersion:"1.0.1",monitorVersion:"1.0.1",
    ok:false,operation:"monitor.auth.bootstrap",code:"AUTH_REJECTED",message:privateMessage,
    data:null,details:{diagnostic:privateDetail,token:TOKEN},
  }),{status:200});
  const result=await bootstrapFromFragment(window,vi.fn().mockResolvedValue(response));
  expect(result).toEqual({ok:false,code:"MONITOR_ACCESS_REJECTED",
    message:"Monitor rejected this access link. Check the Monitor terminal, then run open to create a new authenticated tab."});
  expect(JSON.stringify(result)).not.toContain(TOKEN);
  expect(JSON.stringify(result)).not.toContain(privateMessage);
  expect(JSON.stringify(result)).not.toContain(privateDetail);
  renderStartupError(document,result.ok?"":result.code);
  expect(document.querySelector('[role="alert"]')).toHaveTextContent("Monitor rejected this access link");
  expect(document.body.textContent).not.toContain(TOKEN);
  expect(document.body.textContent).not.toContain(privateMessage);
  expect(document.body.textContent).not.toContain(privateDetail);
  expect(window.location.hash).toBe("");
});

it.each([
  [new Response("private server body",{status:401}),"MONITOR_ACCESS_REJECTED"],
  [new Response("private server body",{status:403}),"MONITOR_ACCESS_REJECTED"],
  [new Response("private server body",{status:404}),"MONITOR_BOOTSTRAP_SERVICE_FAILED"],
  [new Response("private server body",{status:429}),"MONITOR_BOOTSTRAP_SERVICE_FAILED"],
  [new Response("private server body",{status:500}),"MONITOR_BOOTSTRAP_SERVICE_FAILED"],
  [new Response("private server body",{status:503}),"MONITOR_BOOTSTRAP_SERVICE_FAILED"],
  [new Response("private server body"),"MONITOR_BOOTSTRAP_RESPONSE_INVALID"],
])("renders a safe fixed recovery for response failures",async(response,expectedCode)=>{
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  const result=await bootstrapFromFragment(window,vi.fn().mockResolvedValue(response));
  expect(result).toMatchObject({ok:false,code:expectedCode});
  renderStartupError(document,result.ok?"":result.code);
  const text=document.body.textContent??"";
  expect(text).toContain("Monitor terminal");
  expect(text).not.toContain(TOKEN);
  expect(text).not.toContain("private server body");
  if(expectedCode==="MONITOR_BOOTSTRAP_SERVICE_FAILED")
    expect(text).not.toContain("rejected this access link");
  expect(window.location.hash).toBe("");
});

it("renders fixed safe recovery for an unknown bootstrap error code",()=>{
  document.body.textContent=`${TOKEN} private server body`;
  renderStartupError(document,"UNKNOWN_private server body");
  const text=document.body.textContent??"";
  expect(text).toContain("Monitor terminal");
  expect(text).not.toContain(TOKEN);
  expect(text).not.toContain("private server body");
});

it("takeFragmentToken returns null for non-fragment and invalid shapes",()=>{
  window.history.replaceState(null,"","/");
  expect(takeFragmentToken(window)).toBeNull();
  window.history.replaceState(null,"",`/#token=${"a".repeat(63)}`);
  expect(takeFragmentToken(window)).toBeNull();
});
