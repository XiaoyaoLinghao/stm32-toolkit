import {describe,expect,it} from "vitest";
import type {LiveEvent,MonitorStatus,ObservationBinding,RegisterDescriptor,SampleBatch,VariableDescriptor,WatchGroup} from "../src/api/contract";
import {displayDropTotals} from "../src/chart/series";
import {initialState,reducer,reduceAcceptedLiveEnvelope} from "../src/state/reducer";

const binding=():ObservationBinding=>({workspaceId:"w",logicalProjectId:"p",sessionId:"s",probeId:"probe",targetDevice:"STM32",physicalTarget:"target",buildId:"build",elfSha256:"elf",inputSnapshotSha256:"snapshot",gitHead:"head",gitDirty:false,flashSessionId:"flash",leaseId:"lease",dwarfSha256:"dwarf",svdSha256:null});
const status=(epoch=4n,drops={subscriber:0n,history:0n,deadline:0n,service:0n}):MonitorStatus=>({workspaceId:"w",sessionId:"s",project:{logicalProjectId:"p",name:"Project",targetDevice:"STM32"},firmware:{buildId:"build",elfSha256:"elf",inputSnapshotSha256:"snapshot",gitHead:"head",gitDirty:false,targetDevice:"STM32"},probe:{connected:true,probeId:"probe"},sampling:{state:"RUNNING",active:true,blockedCode:null,groupId:"g",groupRevision:1n,runId:"run",lastSequence:null,bindingEpoch:epoch,subscriberDrops:drops.subscriber,historyDrops:drops.history,deadlineDrops:drops.deadline,serviceDrops:drops.service},probeConnected:true,samplingActive:true});
const group=():WatchGroup=>({groupId:"g",name:"Group",description:"",intervalMs:250,items:[{kind:"variable",expression:"x"}],revision:1n,createdAtUtc:"now",updatedAtUtc:"now"});
const batch=(sequence:bigint,drops={subscriber:0n,history:0n,deadline:0n}):SampleBatch=>({binding:binding(),groupId:"g",groupRevision:1n,runId:"run",sequence,scheduledUnixNs:sequence,scheduledAtUtc:"t",capturedUnixNs:sequence,capturedAtUtc:"t",latencyNs:1n,actualRateHz:4,subscriberDrops:drops.subscriber,historyDrops:drops.history,deadlineDrops:drops.deadline,values:[{watch:{kind:"variable",expression:"x"},status:"OK",typedValue:{expression:"x",typeName:"float",value:12.5,rawHex:"0x1",bitWidth:32},code:null,definition:null}]});
const stateEvent=(eventId:bigint,revision:bigint,epoch=4n,gap=false):LiveEvent=>({eventId,type:"state",data:{stateRevision:revision,gap,status:status(epoch)}});
const sampleEnvelope=(eventId:bigint,drops={subscriber:0n,history:0n,deadline:0n},service=0n,outer=0n)=>({event:{eventId,type:"sample" as const,data:{batch:batch(eventId,drops),serviceSubscriberDrops:service}},subscriberDropped:outer});
const running=()=>reducer(reducer(initialState,{type:"initial.loaded",status:status(),probes:[],groups:[group()]}),{type:"series.toggled",key:"variable:x"});
const seeded=()=>reduceAcceptedLiveEnvelope(running(),sampleEnvelope(1n));
const variable:VariableDescriptor={selector:"x",typeName:"int",kind:"scalar",byteSize:4,signed:true,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]};
const register:RegisterDescriptor={selector:"RCC.CSR",sizeBits:32,access:"read",readAction:null,resetValue:null,resetMask:null,fields:[],sampleable:true,requiresAccessAcknowledgement:false};

describe("authoritative monitor reducer",()=>{
  it("loads authoritative state and rejects lower revisions while retaining event ordering",()=>{
    const ready=running();
    const accepted=reduceAcceptedLiveEnvelope(ready,{event:stateEvent(2n,6n),subscriberDropped:0n});
    const old=reduceAcceptedLiveEnvelope(accepted,{event:stateEvent(3n,5n),subscriberDropped:0n});
    expect(ready.selectedGroupId).toBe("g");
    expect(accepted.stateRevision).toBe(6n);
    expect(old.status).toEqual(accepted.status);
    expect(old.lastAcceptedEventId).toBe(3n);
  });

  it("rejects duplicate event IDs before samples or drop deltas mutate state",()=>{
    const event=sampleEnvelope(9n,{subscriber:2n,history:3n,deadline:4n},5n,7n);
    const once=reduceAcceptedLiveEnvelope(running(),event);
    const replay=reduceAcceptedLiveEnvelope(once,event);
    expect(once.live.pendingDropDeltas).toEqual({subscriber:2n,history:3n,deadline:4n,service:5n});
    expect(replay).toEqual(once);
    expect(once.live.series.get("variable:x")?.map(point=>point.value)).toEqual([12.5,null]);
  });

  it("does not accept a stale sample whose workspace/session/binding identity differs",()=>{
    const accepted=reduceAcceptedLiveEnvelope(running(),sampleEnvelope(1n));
    const stale=batch(2n);
    const wrong={...stale,binding:{...stale.binding,leaseId:"different"}};
    const next=reduceAcceptedLiveEnvelope(accepted,{event:{eventId:2n,type:"sample",data:{batch:wrong,serviceSubscriberDrops:9n}},subscriberDropped:0n});
    expect(next.live.rows).toEqual(accepted.live.rows);
    expect(next.live.pendingDropDeltas.service).toBe(0n);
    expect(next.transport.stale).toBe(true);
  });

  it("adds sample deltas once, never decreases on zero, and rebases from status",()=>{
    const once=reduceAcceptedLiveEnvelope(running(),sampleEnvelope(9n,{subscriber:2n,history:3n,deadline:4n},5n,7n));
    const zero=reduceAcceptedLiveEnvelope(once,sampleEnvelope(10n));
    const rebased=reducer(zero,{type:"status.loaded",status:status(4n,{subscriber:11n,history:12n,deadline:13n,service:14n})});
    expect(displayDropTotals(zero.live)).toEqual(displayDropTotals(once.live));
    expect(rebased.live.authoritativeDrops).toEqual({subscriber:11n,history:12n,deadline:13n,service:14n});
    expect(rebased.live.pendingDropDeltas).toEqual({subscriber:0n,history:0n,deadline:0n,service:0n});
  });

  it("resets continuity and zoom on a gap or changed binding/run identity",()=>{
    const sampled=reduceAcceptedLiveEnvelope(running(),sampleEnvelope(1n));
    const zoomed=reducer(sampled,{type:"zoom.changed",action:{type:"zoom.set",start:25,end:75}});
    const gapped=reduceAcceptedLiveEnvelope(zoomed,{event:stateEvent(2n,4n,4n,true),subscriberDropped:0n});
    const rebound=reducer({...gapped,zoom:{start:25,end:75}},{type:"status.loaded",status:status(5n)});
    expect(gapped.zoom).toEqual({start:0,end:100});
    expect(gapped.live.series.get("variable:x")?.at(-1)?.value).toBeNull();
    expect(rebound.zoom).toEqual({start:0,end:100});
    expect(rebound.live.rows.size).toBe(0);
  });

  it("tracks only matching request lifecycle IDs",()=>{
    const started=reducer(running(),{type:"request.started",scope:"sampling.start",requestId:9223372036854775807n});
    const old=reducer(started,{type:"request.cleared",scope:"sampling.start",requestId:1n});
    const failed=reducer(old,{type:"request.failed",scope:"sampling.start",requestId:9223372036854775807n,code:"MONITOR_BUSY",message:"busy"});
    expect(old.pending["sampling.start"]?.requestId).toBe(9223372036854775807n);
    expect(failed.pending["sampling.start"]).toBeUndefined();
    expect(failed.failures["sampling.start"]).toEqual({ok:false,code:"MONITOR_BUSY",message:"busy"});
  });

  it.each([
    ["hello",(eventId:bigint):LiveEvent=>({eventId,type:"hello",data:{protocol:"stm32-toolkit-monitor/1",toolkitVersion:"v",monitorVersion:"v",stateRevision:2n}})],
    ["heartbeat",(eventId:bigint):LiveEvent=>({eventId,type:"heartbeat",data:{stateRevision:2n,capturedAtUtc:"t"}})],
    ["lower state revision",(eventId:bigint):LiveEvent=>stateEvent(eventId,-2n)],
  ] as const)("records exactly one outer continuity gap for accepted %s envelopes",(_name,makeEvent)=>{
    const before={...seeded(),zoom:{start:25,end:75}};
    const totals=displayDropTotals(before.live);
    const next=reduceAcceptedLiveEnvelope(before,{event:makeEvent(2n),subscriberDropped:7n});
    expect(next.live.series.get("variable:x")?.map(point=>point.value)).toEqual([12.5,null]);
    expect(next.zoom).toEqual({start:0,end:100});
    expect(next.transport.needsStatusRefresh).toBe(true);
    expect(displayDropTotals(next.live)).toEqual(totals);
  });

  it("adds an outer gap for a wrong-identity sample without accepting its payload",()=>{
    const before={...seeded(),zoom:{start:25,end:75}};
    const wrong={...batch(2n),binding:{...binding(),leaseId:"other"}};
    const next=reduceAcceptedLiveEnvelope(before,{event:{eventId:2n,type:"sample",data:{batch:wrong,serviceSubscriberDrops:9n}},subscriberDropped:7n});
    expect(next.live.rows.get("variable:x")?.displayValue).toBe(before.live.rows.get("variable:x")?.displayValue);
    expect(next.live.pendingDropDeltas).toEqual(before.live.pendingDropDeltas);
    expect(next.live.series.get("variable:x")?.map(point=>point.value)).toEqual([12.5,null]);
    expect(next.zoom).toEqual({start:0,end:100});
    expect(next.transport.needsStatusRefresh).toBe(true);
  });

  it.each([
    ["workspace",(value:MonitorStatus)=>({...value,workspaceId:"other"})],
    ["session",(value:MonitorStatus)=>({...value,sessionId:"other"})],
    ["project",(value:MonitorStatus)=>({...value,project:{...value.project,logicalProjectId:"other"}})],
    ["firmware removal",(value:MonitorStatus)=>({...value,firmware:null})],
    ["firmware identity",(value:MonitorStatus)=>({...value,firmware:{...value.firmware!,elfSha256:"other"}})],
    ["probe",(value:MonitorStatus)=>({...value,probe:{connected:true,probeId:"other"}})],
    ["probe disconnect",(value:MonitorStatus)=>({...value,probe:{connected:false,probeId:null}})],
    ["binding epoch",(value:MonitorStatus)=>({...value,sampling:{...value.sampling,bindingEpoch:5n}})],
    ["run",(value:MonitorStatus)=>({...value,sampling:{...value.sampling,runId:"other"}})],
  ] as const)("resets the live view when %s authoritative identity changes",(_name,change)=>{
    const before={...seeded(),zoom:{start:25,end:75}};
    const next=reducer(before,{type:"status.loaded",status:change(status())});
    expect(next.live.rows.size).toBe(0);
    expect(next.live.series.size).toBe(0);
    expect(next.zoom).toEqual({start:0,end:100});
  });

  it("does not reset for unrelated sampling state or drop total changes",()=>{
    const before={...seeded(),zoom:{start:25,end:75}};
    const next=reducer(before,{type:"status.loaded",status:{...status(4n,{subscriber:99n,history:0n,deadline:0n,service:0n}),sampling:{...status().sampling,state:"PAUSED",active:false}}});
    expect(next.live.rows).toEqual(before.live.rows);
    expect(next.zoom).toEqual({start:25,end:75});
  });

  it.each(["variables","registers"] as const)("retains matching %s page items and appends the requested continuation",catalog=>{
    const base=reducer(initialState,{type:"initial.loaded",status:status(),probes:[],groups:[]});
    const first=reducer(base,{type:"catalog.requested",catalog,query:"x",bindingKey:"w/s/p/4",cursor:null});
    const loaded=catalog==="variables"
      ?reducer(first,{type:"catalog.loaded",catalog,query:"x",bindingKey:"w/s/p/4",cursor:null,items:[variable],nextCursor:"next"})
      :reducer(first,{type:"catalog.loaded",catalog,query:"x",bindingKey:"w/s/p/4",cursor:null,items:[register],nextCursor:"next"});
    const continued=reducer(loaded,{type:"catalog.requested",catalog,query:"x",bindingKey:"w/s/p/4",cursor:"next"});
    expect(continued.catalog[catalog]?.items).toHaveLength(1);
    const appended=catalog==="variables"
      ?reducer(continued,{type:"catalog.loaded",catalog,query:"x",bindingKey:"w/s/p/4",cursor:"next",items:[{...variable,selector:"y"}],nextCursor:null})
      :reducer(continued,{type:"catalog.loaded",catalog,query:"x",bindingKey:"w/s/p/4",cursor:"next",items:[{...register,selector:"GPIO.IDR"}],nextCursor:null});
    expect(appended.catalog[catalog]?.items).toHaveLength(2);
    const changed=reducer(appended,{type:"catalog.requested",catalog,query:"new",bindingKey:"w/s/p/4",cursor:null});
    expect(changed.catalog[catalog]?.items).toEqual([]);
    const stale=catalog==="variables"
      ?reducer(changed,{type:"catalog.loaded",catalog,query:"new",bindingKey:"w/s/p/4",cursor:"old",items:[variable],nextCursor:null})
      :reducer(changed,{type:"catalog.loaded",catalog,query:"new",bindingKey:"w/s/p/4",cursor:"old",items:[register],nextCursor:null});
    expect(stale).toEqual(changed);
  });
});
