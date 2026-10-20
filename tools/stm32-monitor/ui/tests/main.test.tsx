import {beforeEach,expect,it,vi} from "vitest";
import {waitFor} from "@testing-library/preact";
import {encodeJson} from "../src/api/wire";
import {statusResult} from "./fixtures";

const render=vi.fn();
const h=vi.fn((component:unknown,props:unknown)=>({component,props}));
vi.mock("preact",()=>({render,h}));
vi.mock("../src/app",()=>({App:()=>null}));

const TOKEN="a".repeat(64);
const STATUS=encodeJson({protocol:"stm32-toolkit-monitor/1",toolkitVersion:"1.0.1",
  monitorVersion:"1.0.1",ok:true,operation:"monitor.status",code:"OK",message:"",
  data:statusResult(),details:{}});

beforeEach(()=>{
  vi.resetModules();
  vi.clearAllMocks();
  document.body.innerHTML='<div id="app"></div>';
});

it("renders only the fixed startup error when fragment bootstrap fails",async()=>{
  window.history.replaceState(null,"","/#token=invalid");
  const fetchLike=vi.fn();
  vi.stubGlobal("fetch",fetchLike);
  await import("../src/main");
  expect(document.querySelector('[role="alert"]')).toHaveTextContent("授权链接无效");
  expect(fetchLike).not.toHaveBeenCalled();
  expect(render).not.toHaveBeenCalled();
});

it("renders a rejected access link without exposing the fragment or response body",async()=>{
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(`private ${TOKEN}`,{status:403})));
  await import("../src/main");
  expect(document.querySelector('[role="alert"]')).toHaveTextContent("访问被拒绝");
  expect(document.body.innerHTML).not.toContain(TOKEN);
  expect(document.body.innerHTML).not.toContain("private");
  expect(window.location.hash).toBe("");
  expect(document.querySelector("button[data-startup-retry]")).toBeNull();
  expect(render).not.toHaveBeenCalled();
});

it("mounts the application only after successful fragment bootstrap",async()=>{
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify({
    protocol:"stm32-toolkit-monitor/1",toolkitVersion:"1.0.0",monitorVersion:"1.0.0",
    ok:true,operation:"monitor.auth.bootstrap",code:"OK",message:"",
    data:{authenticated:true},details:{},
  }))));
  await import("../src/main");
  expect(window.location.hash).toBe("");
  expect(render).toHaveBeenCalledTimes(1);
  expect(h).toHaveBeenCalledTimes(1);
  expect(render.mock.calls[0]?.[1]).toBe(document.getElementById("app"));
});

it("mounts the existing app path after a valid plain-root session",async()=>{
  window.history.replaceState(null,"","/");
  const fetchLike=vi.fn().mockResolvedValue(new Response(STATUS));
  vi.stubGlobal("fetch",fetchLike);
  await import("../src/main");
  expect(fetchLike).toHaveBeenCalledOnce();
  expect(fetchLike.mock.calls[0]?.[0]).toBe("/api/v1/status");
  expect(render).toHaveBeenCalledOnce();
  expect(h).toHaveBeenCalledOnce();
});

it("does not mount the app after a plain-root session expires",async()=>{
  window.history.replaceState(null,"","/");
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response("private body",{status:401})));
  await import("../src/main");
  expect(document.querySelector('[role="alert"]')).toHaveTextContent("当前会话已失效");
  expect(document.body.textContent).not.toContain("private body");
  expect(render).not.toHaveBeenCalled();
});

it("rechecks only a plain-root expired session and mounts once after authentication",async()=>{
  window.history.replaceState(null,"","/");
  let resolveRetry:(response:Response)=>void=()=>{};
  const pending=new Promise<Response>(resolve=>{resolveRetry=resolve;});
  const fetchLike=vi.fn().mockResolvedValueOnce(new Response("private",{status:401}))
    .mockReturnValueOnce(pending);
  vi.stubGlobal("fetch",fetchLike);
  await import("../src/main");
  const retry=document.querySelector<HTMLButtonElement>("button[data-startup-retry]");
  expect(retry).not.toBeNull();
  retry!.click();
  retry!.click();
  expect(fetchLike).toHaveBeenCalledTimes(2);
  expect(render).not.toHaveBeenCalled();
  resolveRetry(new Response(STATUS));
  await waitFor(()=>expect(render).toHaveBeenCalledTimes(1));
  retry!.click();
  expect(fetchLike).toHaveBeenCalledTimes(2);
  expect(h).toHaveBeenCalledTimes(1);
});

it("keeps a failed plain-root recheck retryable but never offers fallback for scrubbed fragments",async()=>{
  window.history.replaceState(null,"","/");
  const fetchLike=vi.fn().mockResolvedValueOnce(new Response("private",{status:401}))
    .mockResolvedValueOnce(new Response("private",{status:401}))
    .mockResolvedValueOnce(new Response(STATUS));
  vi.stubGlobal("fetch",fetchLike);
  await import("../src/main");
  document.querySelector<HTMLButtonElement>("button[data-startup-retry]")!.click();
  await waitFor(()=>expect(fetchLike).toHaveBeenCalledTimes(2));
  await waitFor(()=>expect(document.querySelector<HTMLButtonElement>("button[data-startup-retry]")?.disabled)
    .toBe(false));
  document.querySelector<HTMLButtonElement>("button[data-startup-retry]")!.click();
  await waitFor(()=>expect(render).toHaveBeenCalledTimes(1));

  vi.resetModules();
  vi.clearAllMocks();
  document.body.innerHTML='<div id="app"></div>';
  window.history.replaceState(null,"",`/#token=${TOKEN}&other=1`);
  const invalidFetch=vi.fn();
  vi.stubGlobal("fetch",invalidFetch);
  await import("../src/main");
  expect(window.location.hash).toBe("");
  expect(document.querySelector("button[data-startup-retry]")).toBeNull();
  expect(invalidFetch).not.toHaveBeenCalled();
  expect(render).not.toHaveBeenCalled();
});

it("shows plain-root 403 as access rejected with no session retry",async()=>{
  window.history.replaceState(null,"","/");
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response("private",{status:403})));
  await import("../src/main");
  expect(document.querySelector('[role="alert"]')).toHaveTextContent("访问被拒绝");
  expect(document.querySelector("button[data-startup-retry]")).toBeNull();
  expect(render).not.toHaveBeenCalled();
});
