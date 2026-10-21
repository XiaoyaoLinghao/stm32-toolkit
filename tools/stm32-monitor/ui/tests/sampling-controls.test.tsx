import {expect,it,vi} from "vitest";
import {render,screen,within} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {SamplingControls} from "../src/components/SamplingControls";
import type {SamplingStatus} from "../src/api/contract";
import {watchGroup} from "./fixtures";

function sampling(state:SamplingStatus["state"]):SamplingStatus{
  const running=state==="RUNNING"||state==="PAUSED";
  return{
    state,active:running,blockedCode:state==="PAUSED_BLOCKED"?"MONITOR_PROBE_BUSY":null,
    groupId:state==="IDLE"?null:"group",groupRevision:state==="IDLE"?null:1n,
    runId:state==="IDLE"?null:"run",lastSequence:null,
    bindingEpoch:0n,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n,
  };
}

function props(state:SamplingStatus["state"]="IDLE"){
  return{
    status:sampling(state),group:watchGroup(),probeConnected:true,
    onConnectRequest:vi.fn(),onStart:vi.fn(),onPause:vi.fn(),onResume:vi.fn(),onStop:vi.fn(),
    failure:null,
  };
}

it("starts only an idle connected selected group with its expected revision",async()=>{
  const p=props();
  const view=render(<SamplingControls {...p}/>);
  await userEvent.click(screen.getByRole("button",{name:"开始采样"}));
  expect(p.onStart).toHaveBeenCalledExactlyOnceWith("group",1n);
  view.rerender(<SamplingControls {...p} group={null}/>);
  expect(screen.getByRole("button",{name:"开始采样"})).toBeDisabled();
});

it.each([
  ["IDLE",["开始采样"]],
  ["STARTING",["停止采样"]],
  ["RUNNING",["暂停采样","停止采样"]],
  ["PAUSED",["继续采样","停止采样"]],
  ["PAUSED_BLOCKED",["停止采样"]],
  ["STOPPING",["停止采样"]],
] as const)("shows the state actions for %s and invokes the existing callbacks",async(state,expected)=>{
  const p=props(state);
  render(<SamplingControls {...p}/>);
  const panel=screen.getByRole("region",{name:"采样控制"});
  expect(within(panel).getAllByRole("button").map(button=>button.textContent)).toEqual([...expected]);
  for(const action of expected)await userEvent.click(within(panel).getByRole("button",{name:action}));
  expect(p.onStart).toHaveBeenCalledTimes(state==="IDLE"?1:0);
  expect(p.onPause).toHaveBeenCalledTimes(state==="RUNNING"?1:0);
  expect(p.onResume).toHaveBeenCalledTimes(state==="PAUSED"?1:0);
  expect(p.onStop).toHaveBeenCalledTimes(state==="IDLE"?0:1);
  if(state==="PAUSED_BLOCKED"){
    expect(panel).toHaveTextContent("采样受阻");
    expect(within(panel).getByText("MONITOR_PROBE_BUSY")).toBeTruthy();
    expect(p.status.active).toBe(false);
  }
  if(state==="STARTING")expect(p.status.active).toBe(false);
  if(state==="STOPPING")expect(p.status.active).toBe(false);
});

it("offers connection while disconnected and keeps blocked cleanup even with active=false",async()=>{
  const idle=props();
  const view=render(<SamplingControls {...idle} probeConnected={false}/>);
  expect(screen.queryByRole("button",{name:"开始采样"})).toBeNull();
  await userEvent.click(screen.getByRole("button",{name:"连接探针"}));
  expect(idle.onConnectRequest).toHaveBeenCalledOnce();
  expect(idle.onStart).not.toHaveBeenCalled();

  const blocked=props("PAUSED_BLOCKED");
  view.rerender(<SamplingControls {...blocked} probeConnected={false}/>);
  expect(screen.getByRole("button",{name:"连接探针"})).toBeEnabled();
  expect(screen.queryByRole("button",{name:"继续采样"})).toBeNull();
  await userEvent.click(screen.getByRole("button",{name:"停止采样"}));
  expect(blocked.onStop).toHaveBeenCalledOnce();
});

it("disables every displayed write action while busy without hiding cleanup",()=>{
  const p=props("RUNNING");
  const view=render(<SamplingControls {...p} busy/>);
  expect(screen.getByRole("button",{name:"暂停采样"})).toBeDisabled();
  expect(screen.getByRole("button",{name:"停止采样"})).toBeDisabled();
  view.rerender(<SamplingControls {...props("STOPPING")} probeConnected={false} busy/>);
  expect(screen.getByRole("button",{name:"连接探针"})).toBeDisabled();
  expect(screen.getByRole("button",{name:"停止采样"})).toBeDisabled();
});

it("keeps an operation failure in the controls",()=>{
  render(<SamplingControls {...props()} failure={{ok:false,code:"SAMPLING_FAILED",message:"cannot start"}}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("SAMPLING_FAILED");
});
