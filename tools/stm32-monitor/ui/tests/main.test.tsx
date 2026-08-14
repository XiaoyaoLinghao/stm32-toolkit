import {beforeEach,expect,it,vi} from "vitest";

const render=vi.fn();
const h=vi.fn((component:unknown,props:unknown)=>({component,props}));
vi.mock("preact",()=>({render,h}));
vi.mock("../src/app",()=>({App:()=>null}));

const TOKEN="a".repeat(64);

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
  expect(document.querySelector('[role="alert"]')).toHaveTextContent("Monitor could not start");
  expect(fetchLike).not.toHaveBeenCalled();
  expect(render).not.toHaveBeenCalled();
});

it("mounts the application only after successful fragment bootstrap",async()=>{
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify({
    protocol:"stm32-toolkit-monitor/1",toolkitVersion:"0.5.0",monitorVersion:"0.5.0",
    ok:true,operation:"monitor.auth.bootstrap",code:"OK",message:"",
    data:{authenticated:true},details:{},
  }))));
  await import("../src/main");
  expect(window.location.hash).toBe("");
  expect(render).toHaveBeenCalledTimes(1);
  expect(h).toHaveBeenCalledTimes(1);
  expect(render.mock.calls[0]?.[1]).toBe(document.getElementById("app"));
});
