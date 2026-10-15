import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import type {MonitorStatus,ObservationBinding,SampleBatch,WatchGroup} from "../src/api/contract";
import {LiveTable} from "../src/components/LiveTable";
import {StatusStrip} from "../src/components/StatusStrip";
import {initialState,reducer} from "../src/state/reducer";
import {activeGroup,liveRows,selectedGroup} from "../src/state/selectors";

const at="2026-08-10T00:00:01.123Z";
const binding:ObservationBinding={workspaceId:"w",logicalProjectId:"p",sessionId:"s",probeId:"probe",targetDevice:"STM32",physicalTarget:"target",buildId:"build",elfSha256:"elf",inputSnapshotSha256:"snapshot",gitHead:"head",gitDirty:false,flashSessionId:"flash",leaseId:"lease",dwarfSha256:"dwarf",svdSha256:null};
const status=(runId="run",bindingEpoch=4n):MonitorStatus=>({workspaceId:"w",sessionId:"s",project:{logicalProjectId:"p",name:"Project",targetDevice:"STM32"},firmware:{buildId:"build",elfSha256:"elf",inputSnapshotSha256:"snapshot",gitHead:"head",gitDirty:false,targetDevice:"STM32"},probe:{connected:true,probeId:"probe"},sampling:{state:"RUNNING",active:true,blockedCode:null,groupId:"g",groupRevision:1n,runId,lastSequence:null,bindingEpoch,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n},probeConnected:true,samplingActive:true});
const group:WatchGroup={groupId:"g",name:"Group",description:"",intervalMs:250,items:[{kind:"variable",expression:"x"}],revision:1n,createdAtUtc:"now",updatedAtUtc:"now"};
const batch:SampleBatch={binding,groupId:"g",groupRevision:1n,runId:"run",sequence:1n,scheduledUnixNs:1n,scheduledAtUtc:"earlier",capturedUnixNs:2n,capturedAtUtc:at,latencyNs:2_500_000n,actualRateHz:4,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,values:[{watch:{kind:"variable",expression:"x"},status:"OK",typedValue:{expression:"x",typeName:"float",value:12.5,rawHex:"0x1",bitWidth:32},code:null,definition:null}]};
const ready=()=>reducer(initialState,{type:"initial.loaded",status:status(),probes:[],groups:[group]});
const sample=()=>reducer(ready(),{type:"live.envelope",value:{event:{eventId:1n,type:"sample",data:{batch,serviceSubscriberDrops:0n}},subscriberDropped:0n}});

it("records time only for accepted samples and keeps it through heartbeat, gap and same-run status",()=>{
  expect(ready().live.lastSampleCapturedAtUtc).toBeNull();
  const accepted=sample();
  expect(accepted.live.lastSampleCapturedAtUtc).toBe(at);
  const heartbeat=reducer(accepted,{type:"live.envelope",value:{event:{eventId:2n,type:"heartbeat",data:{stateRevision:1n,capturedAtUtc:"later"}},subscriberDropped:0n}});
  const statusLoaded=reducer(heartbeat,{type:"status.loaded",status:status()});
  const gap=reducer(statusLoaded,{type:"live.envelope",value:{event:{eventId:3n,type:"state",data:{stateRevision:2n,gap:true,status:status()}},subscriberDropped:0n}});
  expect(gap.live.lastSampleCapturedAtUtc).toBe(at);
  const wrong={...batch,sequence:2n,capturedAtUtc:"wrong",binding:{...binding,leaseId:"other"}};
  const rejected=reducer(gap,{type:"live.envelope",value:{event:{eventId:4n,type:"sample",data:{batch:wrong,serviceSubscriberDrops:0n}},subscriberDropped:0n}});
  expect(rejected.live.lastSampleCapturedAtUtc).toBe(at);
  const reset=reducer(rejected,{type:"status.loaded",status:status("new-run",5n)});
  expect(reset.live.lastSampleCapturedAtUtc).toBeNull();
});

it("shows the UTC capture time in each live row and labels a retained nonfresh sample",()=>{
  const rows=[...sample().live.rows.values()];
  const view=render(<LiveTable rows={rows} selectedSeries={[]} fresh onSeriesToggle={vi.fn()}/>);
  expect(screen.getByText(at)).toBeTruthy();
  expect(screen.getByText("采集时间（UTC）")).toBeTruthy();
  view.rerender(<LiveTable rows={rows} selectedSeries={[]} fresh={false} onSeriesToggle={vi.fn()}/>);
  expect(screen.getByText("非最新数据")).toBeTruthy();
  expect(screen.getByText(at)).toBeTruthy();
});

it("does not present fake zero metrics before samples, and marks old rate and latency as last sample",()=>{
  const drops={subscriber:1n,history:2n,deadline:3n,service:4n};
  const view=render(<StatusStrip actualRateHz={0} latencyNs={0n} lastSampleCapturedAtUtc={null} fresh={false} drops={drops}/>);
  expect(screen.getAllByText("尚未收到样本")).toHaveLength(2);
  expect(screen.queryByText("0.00 Hz")).toBeNull();
  expect(screen.getByText(/丢弃：订阅者/)).toHaveTextContent("1");
  view.rerender(<StatusStrip actualRateHz={4} latencyNs={2_500_000n} lastSampleCapturedAtUtc={at} fresh={false} drops={drops}/>);
  expect(screen.getByText(/上次样本/)).toHaveTextContent(at);
  expect(screen.getByText("4.00 Hz")).toBeTruthy();
  expect(screen.getByText("2.50 ms")).toBeTruthy();
  view.rerender(<StatusStrip actualRateHz={4} latencyNs={2_500_000n} lastSampleCapturedAtUtc={at} fresh drops={drops}/>);
  expect(screen.queryByText(/上次样本/)).toBeNull();
  expect(screen.getByText(/采集时间（UTC）/)).toHaveTextContent(at);
});

it("keeps the live table tied to the running group when the next editing target changes",()=>{
  const nextGroup:WatchGroup={...group,groupId:"next",name:"Next",items:[{kind:"variable",expression:"y"}]};
  const state=reducer({...sample(),groups:[group,nextGroup]},{type:"group.selected",groupId:"next"});
  expect(selectedGroup(state)?.groupId).toBe("next");
  expect(activeGroup(state)?.groupId).toBe("g");
  expect(liveRows(state).map(row=>row.watch)).toEqual(group.items);
  expect(liveRows(state)[0]?.displayValue).toBe("12.5");
});

it("after revision change or deletion shows only accepted same-run rows, never a new revision's items",()=>{
  const revised:WatchGroup={...group,revision:2n,name:"New version",items:[{kind:"variable",expression:"y"}]};
  const changed=reducer(sample(),{type:"groups.loaded",groups:[revised]});
  expect(activeGroup(changed)).toBeNull();
  expect(changed.live.lastSampleCapturedAtUtc).toBe(at);
  expect(liveRows(changed).map(row=>row.watch)).toEqual(group.items);
  const removed=reducer(changed,{type:"group.deleted",groupId:"g"});
  expect(liveRows(removed).map(row=>row.watch)).toEqual(group.items);
  expect(removed.live.lastSampleCapturedAtUtc).toBe(at);
  const wrongRun={...removed,live:{...removed.live,runId:"prior-run"}};
  expect(liveRows(wrongRun)).toEqual([]);
});

it("uses empty placeholders when the live run differs and only previews the selected group without a run",()=>{
  const accepted=sample();
  const differentRun={...accepted,live:{...accepted.live,runId:"prior-run"}};
  expect(activeGroup(differentRun)?.groupId).toBe("g");
  expect(liveRows(differentRun)).toHaveLength(1);
  expect(liveRows(differentRun)[0]?.displayValue).toBe("");
  const noRun={...accepted,status:{...accepted.status!,sampling:{...accepted.status!.sampling,runId:null}}};
  expect(activeGroup(noRun)).toBeNull();
  expect(liveRows(noRun)).toHaveLength(1);
  expect(liveRows(noRun)[0]?.displayValue).toBe("");
});
