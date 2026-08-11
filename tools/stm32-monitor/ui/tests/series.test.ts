import {expect,it} from "vitest";
import type {HistoryPage,JsonValue,SampleBatch,WatchGroup} from "../src/api/contract";
import {appendAuthoritativeSample,appendContinuityGap,emptyLive,projectHistoryPage,watchKey} from "../src/chart/series";

const watches=Array.from({length:9},(_,i)=>({kind:"variable" as const,expression:`x${i}`}));
const group:WatchGroup={groupId:"g",name:"g",description:"",intervalMs:250,items:watches,revision:1n,createdAtUtc:"",updatedAtUtc:""};
const batch=(sequence:bigint,status:"OK"|"ERROR"="OK",value:JsonValue=12.5):SampleBatch=>({binding:{workspaceId:"w",logicalProjectId:"p",sessionId:"s",probeId:"p",targetDevice:"t",physicalTarget:"t",buildId:"b",elfSha256:"e",inputSnapshotSha256:"i",gitHead:"h",gitDirty:false,flashSessionId:"f",leaseId:"l",dwarfSha256:"d",svdSha256:null},groupId:"g",groupRevision:1n,runId:"r",sequence,scheduledUnixNs:sequence,scheduledAtUtc:"t",capturedUnixNs:sequence,capturedAtUtc:`t${sequence}`,latencyNs:0n,actualRateHz:1,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,values:watches.map(watch=>status==="OK"?{watch,status,typedValue:{expression:watch.expression,typeName:"float",value,rawHex:"0x1",bitWidth:32},code:null,definition:null}:{watch,status,typedValue:null,code:"BAD",definition:null})});

it("preserves prior row and appends a null chart gap for ERROR",()=>{
  const one=appendAuthoritativeSample(emptyLive(),batch(1n),group,new Set(["variable:x0"]));
  const two=appendAuthoritativeSample(one,batch(2n,"ERROR",null),group,new Set(["variable:x0"]));
  expect(two.rows.get("variable:x0")?.displayValue).toBe("12.5");
  expect(two.series.get("variable:x0")?.map(point=>point.value)).toEqual([12.5,null]);
});

it("resets trends after an error and bounds selected chart series to eight by six hundred",()=>{
  let live=emptyLive();
  const selected=new Set(watches.map(watchKey));
  for(let i=1n;i<=601n;i++)live=appendAuthoritativeSample(live,batch(i),group,selected);
  expect(live.series.size).toBe(8);
  for(const points of live.series.values())expect(points).toHaveLength(600);
  const error=appendAuthoritativeSample(live,batch(602n,"ERROR"),group,selected);
  expect(error.rows.get("variable:x0")?.trend).toBe("none");
});

it("turns null, bigint, nonnumeric, and nonfinite typed values into chart gaps",()=>{
  for(const value of [null,1n,"one",Number.NaN,Number.POSITIVE_INFINITY]){
    const next=appendAuthoritativeSample(emptyLive(),batch(1n,"OK",value),group,new Set(["variable:x0"]));
    expect(next.series.get("variable:x0")?.[0]?.value).toBeNull();
  }
});

it("clears the numeric trend baseline after an ERROR, null value, or continuity gap",()=>{
  const selected=new Set(["variable:x0"]);
  const one=appendAuthoritativeSample(emptyLive(),batch(1n,"OK",12.5),group,selected);
  const afterError=appendAuthoritativeSample(one,batch(2n,"ERROR"),group,selected);
  const errorRecovery=appendAuthoritativeSample(afterError,batch(3n,"OK",13),group,selected);
  const afterNull=appendAuthoritativeSample(one,batch(2n,"OK",null),group,selected);
  const nullRecovery=appendAuthoritativeSample(afterNull,batch(3n,"OK",13),group,selected);
  const afterGap=appendContinuityGap(one);
  const gapRecovery=appendAuthoritativeSample(afterGap,batch(2n,"OK",13),group,selected);
  expect(errorRecovery.rows.get("variable:x0")?.trend).toBe("none");
  expect(nullRecovery.rows.get("variable:x0")?.trend).toBe("none");
  expect(gapRecovery.rows.get("variable:x0")?.trend).toBe("none");
});

it("projects a HistoryPage into the same bounded 8 by 600 model",()=>{
  const batches=Array.from({length:601},(_,index)=>({...batch(BigInt(index+1)),startOrdinal:BigInt(index+1),batchValueCount:9n}));
  const page:HistoryPage={batches,valueCount:5409n,nextCursor:null,serializedBytes:1n};
  const projection=projectHistoryPage(page,new Map([[group.groupId,group]]),new Set(group.items.slice(0,8).map(watchKey)));
  expect(projection.series.size).toBe(8);
  for(const points of projection.series.values())expect(points).toHaveLength(600);
  expect(projection.rows[0]?.startOrdinal).toBe(1n);
});
