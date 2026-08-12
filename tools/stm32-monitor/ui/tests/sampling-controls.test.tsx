import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {SamplingControls} from "../src/components/SamplingControls";
import type {SamplingStatus} from "../src/api/contract";
import {watchGroup} from "./fixtures";

function sampling(state:SamplingStatus["state"],overrides:Partial<SamplingStatus>={}):SamplingStatus{
  return{
    state,active:false,blockedCode:null,groupId:null,groupRevision:null,runId:null,lastSequence:null,
    bindingEpoch:0n,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n,
    ...overrides,
  };
}

function props(overrides:Record<string,unknown>={}){
  return{
    status:sampling("IDLE"),
    group:watchGroup(),
    onStart:vi.fn(),
    onPause:vi.fn(),
    onResume:vi.fn(),
    onStop:vi.fn(),
    failure:null,
    ...overrides,
  };
}

it("starts sampling with the selected group id and expected revision",async()=>{
  const start=vi.fn();
  render(<SamplingControls {...props({onStart:start})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Start"}));
  expect(start).toHaveBeenCalledWith("group",1n);
});

it("disables start without a selected group",()=>{
  render(<SamplingControls {...props({group:null})}/>);
  expect(screen.getByRole("button",{name:"Start"})).toBeDisabled();
});

it("disables start while sampling is running or paused",()=>{
  const first=render(<SamplingControls {...props({status:sampling("RUNNING",{active:true})})}/>);
  expect(screen.getByRole("button",{name:"Start"})).toBeDisabled();
  first.unmount();
  render(<SamplingControls {...props({status:sampling("PAUSED",{active:true})})}/>);
  expect(screen.getByRole("button",{name:"Start"})).toBeDisabled();
});

it("allows start again from STOPPING",()=>{
  render(<SamplingControls {...props({status:sampling("STOPPING",{active:true})})}/>);
  expect(screen.getByRole("button",{name:"Start"})).toBeEnabled();
});

it("pauses only while running",async()=>{
  const pause=vi.fn();
  const running=render(<SamplingControls {...props({status:sampling("RUNNING",{active:true}),onPause:pause})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Pause"}));
  expect(pause).toHaveBeenCalled();
  running.unmount();
  const idle=vi.fn();
  render(<SamplingControls {...props({onPause:idle})}/>);
  expect(screen.getByRole("button",{name:"Pause"})).toBeDisabled();
  expect(idle).not.toHaveBeenCalled();
});

it("resumes only while paused or paused-blocked",async()=>{
  const resume=vi.fn();
  const paused=render(<SamplingControls {...props({status:sampling("PAUSED",{active:true}),onResume:resume})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Resume"}));
  expect(resume).toHaveBeenCalled();
  paused.unmount();
  const blocked=vi.fn();
  const blockedRender=render(<SamplingControls {...props({status:sampling("PAUSED_BLOCKED",{active:true,blockedCode:"MONITOR_PROBE_BUSY"}),onResume:blocked})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Resume"}));
  expect(blocked).toHaveBeenCalled();
  blockedRender.unmount();
  render(<SamplingControls {...props({status:sampling("IDLE"),onResume:resume})}/>);
  expect(screen.getByRole("button",{name:"Resume"})).toBeDisabled();
});

it("stops only when sampling is active",async()=>{
  const stop=vi.fn();
  const running=render(<SamplingControls {...props({status:sampling("RUNNING",{active:true}),onStop:stop})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Stop"}));
  expect(stop).toHaveBeenCalled();
  running.unmount();
  render(<SamplingControls {...props({status:sampling("IDLE"),onStop:stop})}/>);
  expect(screen.getByRole("button",{name:"Stop"})).toBeDisabled();
  expect(stop).toHaveBeenCalledTimes(1);
});

it("shows the authoritative state and current group",()=>{
  render(<SamplingControls {...props({status:sampling("PAUSED",{active:true})})}/>);
  expect(screen.getByRole("status")).toHaveTextContent("PAUSED");
  expect(screen.getByText("Group",{exact:false})).toBeTruthy();
});

it("renders the sampling failure alert",()=>{
  render(<SamplingControls {...props({failure:{ok:false,code:"SAMPLING_FAILED",message:"cannot start"}})}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("SAMPLING_FAILED");
});
