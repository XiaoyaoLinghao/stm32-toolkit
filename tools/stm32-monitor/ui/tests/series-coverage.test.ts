import {describe,expect,it} from "vitest";
import type {HistoryPage,JsonValue,SampleBatch,SampleValue,WatchGroup,WatchItem} from "../src/api/contract";
import {addSampleDropDeltas,appendAuthoritativeSample,appendContinuityGap,emptyLive,projectHistoryPage,watchKey} from "../src/chart/series";

const item=(kind:"variable"|"register",key:string):WatchItem=>kind==="variable"?{kind,expression:key}:{kind,registerPath:key};
const group=():WatchGroup=>({groupId:"g",name:"g",description:"",intervalMs:250,items:[item("variable","x"),item("register","r")],revision:1n,createdAtUtc:"",updatedAtUtc:""});
const binding={workspaceId:"w",logicalProjectId:"p",sessionId:"s",probeId:"p",targetDevice:"t",physicalTarget:"t",buildId:"b",elfSha256:"e",inputSnapshotSha256:"i",gitHead:"h",gitDirty:false,flashSessionId:"f",leaseId:"l",dwarfSha256:"d",svdSha256:null};
const okValue=(watch:WatchItem,value:JsonValue):SampleValue=>({watch,status:"OK",typedValue:{expression:"x",typeName:"float",value,rawHex:"0x1",bitWidth:32},code:null,definition:null});
const errorValue=(watch:WatchItem):SampleValue=>({watch,status:"ERROR",typedValue:null,code:"BAD",definition:null});

function batch(sequence:bigint,values:readonly SampleValue[]):SampleBatch{
  return{binding,groupId:"g",groupRevision:1n,runId:"r",sequence,scheduledUnixNs:sequence,scheduledAtUtc:"t",capturedUnixNs:sequence,capturedAtUtc:`t${sequence}`,latencyNs:0n,actualRateHz:1,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,values};
}

describe("watchKey and format",()=>{
  it("keys register watches with a register prefix",()=>{
    expect(watchKey({kind:"register",registerPath:"RCC.CSR"})).toBe("register:RCC.CSR");
  });
  it("formats a bigint typed value to its decimal string",()=>{
    const live=appendAuthoritativeSample(emptyLive(),batch(1n,[{watch:{kind:"variable",expression:"x"},status:"OK",typedValue:9223372036854775807n,code:null,definition:null}]),group(),new Set(["variable:x"]));
    expect(live.rows.get("variable:x")?.displayValue).toBe("9223372036854775807");
  });
});

describe("appendAuthoritativeSample row trends",()=>{
  it("labels a decreasing numeric trend as down",()=>{
    const g=group();
    const selected=new Set(["variable:x"]);
    let live=appendAuthoritativeSample(emptyLive(),batch(1n,[okValue(item("variable","x"),12.5)]),g,selected);
    live=appendAuthoritativeSample(live,batch(2n,[okValue(item("variable","x"),10)]),g,selected);
    expect(live.rows.get("variable:x")?.trend).toBe("down");
  });
  it("preserves an ERROR row but clears its numeric baseline",()=>{
    const g=group();
    const selected=new Set(["variable:x"]);
    let live=appendAuthoritativeSample(emptyLive(),batch(1n,[okValue(item("variable","x"),12.5)]),g,selected);
    live=appendAuthoritativeSample(live,batch(2n,[errorValue(item("variable","x"))]),g,selected);
    expect(live.rows.get("variable:x")?.errorCode).toBe("BAD");
    expect(live.rows.get("variable:x")?.trend).toBe("none");
    expect(live.rows.get("variable:x")?.numericValue).toBeNull();
  });
  it("falls back to an empty row when an ERROR has no previous row",()=>{
    const g=group();
    const selected=new Set(["variable:x"]);
    const live=appendAuthoritativeSample(emptyLive(),batch(1n,[errorValue(item("variable","x"))]),g,selected);
    expect(live.rows.get("variable:x")?.errorCode).toBe("BAD");
    expect(live.rows.get("variable:x")?.watch).toEqual({kind:"variable",expression:"x"});
  });
  it("records a null series point for a selected watch absent from a batch",()=>{
    const g=group();
    const selected=new Set(["variable:x","register:r"]);
    const live=appendAuthoritativeSample(emptyLive(),batch(1n,[okValue(item("variable","x"),1)]),g,selected);
    expect(live.rows.get("register:r")).toBeUndefined();
    expect(live.series.get("register:r")?.[0]?.value).toBeNull();
    expect(live.series.get("variable:x")?.[0]?.value).toBe(1);
  });
  it("drops series that are no longer selected while keeping the remaining ones",()=>{
    const g=group();
    let live=appendAuthoritativeSample(emptyLive(),batch(1n,[okValue(item("variable","x"),1),okValue(item("register","r"),2)]),g,new Set(["variable:x","register:r"]));
    expect(live.series.has("register:r")).toBe(true);
    live=appendAuthoritativeSample(live,batch(2n,[okValue(item("variable","x"),3)]),g,new Set(["variable:x"]));
    expect(live.series.has("register:r")).toBe(false);
    expect(live.series.has("variable:x")).toBe(true);
  });
});

describe("projectHistoryPage",()=>{
  it("skips batches whose group is not in the map",()=>{
    const page:HistoryPage={batches:[{...batch(1n,[okValue(item("variable","x"),1)]),startOrdinal:1n,batchValueCount:1n}],valueCount:1n,nextCursor:null,serializedBytes:1n};
    const projection=projectHistoryPage(page,new Map(),new Set(["variable:x"]));
    expect(projection.rows).toEqual([]);
  });
  it("emits null chart points for selected watches missing from a batch",()=>{
    const g=group();
    const page:HistoryPage={batches:[{...batch(1n,[okValue(item("variable","x"),1)]),startOrdinal:1n,batchValueCount:1n}],valueCount:1n,nextCursor:null,serializedBytes:1n};
    const projection=projectHistoryPage(page,new Map([[g.groupId,g]]),new Set(["variable:x","register:r"]));
    expect(projection.series.get("register:r")?.[0]?.value).toBeNull();
    expect(projection.series.get("variable:x")?.[0]?.value).toBe(1);
  });
});

describe("drop accounting",()=>{
  it("appends continuity gap points for every selected series",()=>{
    const g=group();
    let live=appendAuthoritativeSample(emptyLive(),batch(1n,[okValue(item("variable","x"),1)]),g,new Set(["variable:x"]));
    expect(live.segment).toBe(0n);
    live=appendContinuityGap(live);
    expect(live.segment).toBe(1n);
    expect(live.series.get("variable:x")?.at(-1)?.value).toBeNull();
  });
  it("starts a gap with an empty point list when a selected series has no points yet",()=>{
    const live=appendContinuityGap({...emptyLive(),selectedSeries:new Set(["variable:x"])});
    expect(live.series.get("variable:x")?.[0]?.value).toBeNull();
    expect(live.segment).toBe(1n);
  });
  it("accumulates positive drop deltas and ignores zero or negative deltas",()=>{
    let live=emptyLive();
    live=addSampleDropDeltas(live,batch(1n,[okValue(item("variable","x"),1)]),0n);
    expect(live.pendingDropDeltas).toEqual({subscriber:0n,history:0n,deadline:0n,service:0n});
    const withDrops={...batch(1n,[okValue(item("variable","x"),1)]),subscriberDrops:5n,historyDrops:6n,deadlineDrops:7n};
    live=addSampleDropDeltas(live,withDrops,8n);
    expect(live.pendingDropDeltas).toEqual({subscriber:5n,history:6n,deadline:7n,service:8n});
  });
});
