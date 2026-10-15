import {beforeEach,expect,it,vi} from "vitest";
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
  expect(document.querySelector('[role="alert"]')).toHaveTextContent("授权链接被拒绝");
  expect(document.body.innerHTML).not.toContain(TOKEN);
  expect(document.body.innerHTML).not.toContain("private");
  expect(window.location.hash).toBe("");
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
