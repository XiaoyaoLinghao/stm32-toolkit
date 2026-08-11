import {describe,expect,it} from "vitest";
import type {LiveEvent,MonitorStatus,ObservationBinding,SampleBatch,WatchGroup} from "../src/api/contract";
import {emptyDraft} from "../src/state/model";
import {initialState,reducer,reduceAcceptedLiveEnvelope} from "../src/state/reducer";

const binding=():ObservationBinding=>({workspaceId:"w",logicalProjectId:"p",sessionId:"s",probeId:"probe",targetDevice:"STM32",physicalTarget:"target",buildId:"build",elfSha256:"elf",inputSnapshotSha256:"snapshot",gitHead:"head",gitDirty:false,flashSessionId:"flash",leaseId:"lease",dwarfSha256:"dwarf",svdSha256:null});
const status=(epoch=4n):MonitorStatus=>({workspaceId:"w",sessionId:"s",project:{logicalProjectId:"p",name:"Project",targetDevice:"STM32"},firmware:{buildId:"build",elfSha256:"elf",inputSnapshotSha256:"snapshot",gitHead:"head",gitDirty:false,targetDevice:"STM32"},probe:{connected:true,probeId:"probe"},sampling:{state:"RUNNING",active:true,blockedCode:null,groupId:"g",groupRevision:1n,runId:"run",lastSequence:null,bindingEpoch:epoch,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n},probeConnected:true,samplingActive:true});
const group=():WatchGroup=>({groupId:"g",name:"Group",description:"",intervalMs:250,items:[{kind:"variable",expression:"x"}],revision:1n,createdAtUtc:"now",updatedAtUtc:"now"});
const batch=(sequence:bigint):SampleBatch=>({binding:binding(),groupId:"g",groupRevision:1n,runId:"run",sequence,scheduledUnixNs:sequence,scheduledAtUtc:"t",capturedUnixNs:sequence,capturedAtUtc:"t",latencyNs:1n,actualRateHz:4,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,values:[{watch:{kind:"variable",expression:"x"},status:"OK",typedValue:{expression:"x",typeName:"float",value:12.5,rawHex:"0x1",bitWidth:32},code:null,definition:null}]});
const hello=(eventId:bigint,revision:bigint):LiveEvent=>({eventId,type:"hello",data:{protocol:"stm32-toolkit-monitor/1",toolkitVersion:"v",monitorVersion:"v",stateRevision:revision}});
const stateEvent=(eventId:bigint,revision:bigint,epoch=4n):LiveEvent=>({eventId,type:"state",data:{stateRevision:revision,gap:false,status:status(epoch)}});

const base=()=>reducer(initialState,{type:"initial.loaded",status:status(),probes:[],groups:[group()]});
const seeded=()=>reduceAcceptedLiveEnvelope(base(),{event:{eventId:1n,type:"sample",data:{batch:batch(1n),serviceSubscriberDrops:0n}},subscriberDropped:0n});

describe("reducer dispatch coverage",()=>{
  it("dispatches live.envelope through the reducer",()=>{
    const next=reducer(base(),{type:"live.envelope",value:{event:{eventId:1n,type:"heartbeat",data:{stateRevision:1n,capturedAtUtc:"t"}},subscriberDropped:0n}});
    expect(next.lastAcceptedEventId).toBe(1n);
  });
  it("dispatches group.draft.changed, group.watch.added and removed, and zoom.reset",()=>{
    const started=reducer(base(),{type:"group.draft.changed",draft:{...emptyDraft,name:"New"}});
    expect(started.groupDraft.name).toBe("New");
    const added=reducer(started,{type:"group.watch.added",watch:{kind:"variable",expression:"y"}});
    expect(added.groupDraft.items).toHaveLength(1);
    const duplicate=reducer(added,{type:"group.watch.added",watch:{kind:"variable",expression:"y"}});
    expect(duplicate.groupDraft.items).toHaveLength(1);
    const removed=reducer(added,{type:"group.watch.removed",key:"variable:y"});
    expect(removed.groupDraft.items).toHaveLength(0);
    const noop=reducer(added,{type:"group.watch.removed",key:"variable:missing"});
    expect(noop.groupDraft.items).toHaveLength(1);
    const reset=reducer(added,{type:"zoom.reset"});
    expect(reset.zoom).toEqual({start:0,end:100});
  });
  it("toggles series off and refuses a ninth selection",()=>{
    const on=reducer(base(),{type:"series.toggled",key:"variable:x"});
    expect(on.selectedSeries.has("variable:x")).toBe(true);
    const off=reducer(on,{type:"series.toggled",key:"variable:x"});
    expect(off.selectedSeries.size).toBe(0);
    let full=base();
    for(let i=0;i<8;i++)full=reducer(full,{type:"series.toggled",key:`k${i}`});
    expect(full.selectedSeries.size).toBe(8);
    const refused=reducer(full,{type:"series.toggled",key:"k8"});
    expect(refused.selectedSeries.size).toBe(8);
  });
  it("selects an existing group by id and falls back when the id is unknown",()=>{
    const selected=reducer(base(),{type:"group.selected",groupId:"g"});
    expect(selected.selectedGroupId).toBe("g");
    const unknown=reducer(base(),{type:"group.selected",groupId:"missing"});
    expect(unknown.selectedGroupId).toBeNull();
    expect(unknown.groupDraft).toEqual(emptyDraft);
  });
  it("rejects catalog requests when status is absent or the binding key differs",()=>{
    const noStatus=reducer(initialState,{type:"catalog.requested",catalog:"variables",query:"x",bindingKey:"w/s/p/4",cursor:null});
    expect(noStatus.catalog.variables).toBeNull();
    const rebound=base();
    const mismatch=reducer(rebound,{type:"catalog.requested",catalog:"variables",query:"x",bindingKey:"WRONG",cursor:null});
    expect(mismatch.catalog.variables).toBeNull();
  });
  it("reloads groups selecting the first group by id and resets to empty on none",()=>{
    const g=group();
    const present=reducer(base(),{type:"groups.loaded",groups:[g]});
    expect(present.selectedGroupId).toBe("g");
    const rebound=reducer(base(),{type:"group.selected",groupId:"g"});
    const firstFallback=reducer(rebound,{type:"groups.loaded",groups:[g]});
    expect(firstFallback.selectedGroupId).toBe("g");
    const empty=reducer(initialState,{type:"groups.loaded",groups:[]});
    expect(empty.selectedGroupId).toBeNull();
    expect(empty.groupDraft).toEqual(emptyDraft);
  });
});

describe("live envelope edge branches",()=>{
  it("keeps the current state revision when a hello reports a lower one",()=>{
    const high=reduceAcceptedLiveEnvelope(base(),{event:hello(1n,5n),subscriberDropped:0n});
    expect(high.stateRevision).toBe(5n);
    const low=reduceAcceptedLiveEnvelope(high,{event:hello(2n,3n),subscriberDropped:0n});
    expect(low.stateRevision).toBe(5n);
  });
  it("resets the live view, catalog and zoom for a changed binding in a state event",()=>{
    const before={...seeded(),zoom:{start:25,end:75}};
    const next=reduceAcceptedLiveEnvelope(before,{event:stateEvent(2n,1n,5n),subscriberDropped:0n});
    expect(next.live.rows.size).toBe(0);
    expect(next.catalog).toEqual({variables:null,registers:null});
    expect(next.zoom).toEqual({start:0,end:100});
    expect(next.notices[0]?.text).toContain("new binding");
    expect(next.transport.needsStatusRefresh).toBe(false);
  });
});
