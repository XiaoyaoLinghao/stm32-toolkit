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
    return new Response(JSON.stringify({protocol:"stm32-toolkit-monitor/1",toolkitVersion:"0.9.0",
      monitorVersion:"0.9.0",ok:true,operation:"monitor.auth.bootstrap",code:"OK",message:"",
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
  expect(result).toEqual({ok:false,code:"MONITOR_BOOTSTRAP_FAILED",message:"Monitor could not start"});
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

it("returns only fixed startup copy on bootstrap failure",async()=>{
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  const result=await bootstrapFromFragment(window,vi.fn().mockRejectedValue(new Error(TOKEN)));
  expect(result).toEqual({ok:false,code:"MONITOR_BOOTSTRAP_FAILED",message:"Monitor could not start"});
  expect(JSON.stringify(result)).not.toContain(TOKEN);
  renderStartupError(document);
  expect(document.querySelector('[role="alert"]')?.textContent).toBe("Monitor could not start");
  expect(document.body.textContent).not.toContain(TOKEN);
});

it("takeFragmentToken returns null for non-fragment and invalid shapes",()=>{
  window.history.replaceState(null,"","/");
  expect(takeFragmentToken(window)).toBeNull();
  window.history.replaceState(null,"",`/#token=${"a".repeat(63)}`);
  expect(takeFragmentToken(window)).toBeNull();
});
