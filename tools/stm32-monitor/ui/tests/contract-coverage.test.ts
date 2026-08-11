import {describe,expect,it} from "vitest";
import {
  deletedGroupGuard,envelopeDetails,exportArtifactGuard,groupPageGuard,historyPageGuard,historyBatchSliceGuard,
  liveEventGuard,monitorStatusGuard,parseEnvelope,parseEnvelopeText,probeInfoGuard,projectStatusGuard,
  registerDescriptorGuard,releasedGuard,resumedGuard,samplerStartGuard,samplingStatusGuard,sampleValueGuard,stoppedGuard,
  variableDescriptorGuard,watchGroupGuard,watchGroupsGuard,watchItemGuard,
  type DataGuard,
} from "../src/api/contract";
import {IntegerToken} from "../src/api/wire";

const integer=(text:string)=>new IntegerToken(text);
const ok=<T>(guard:DataGuard<T>,value:unknown)=>guard(value);
const bad=<T>(guard:DataGuard<T>,value:unknown)=>()=>guard(value);

describe("primitive and shape guards",()=>{
  it("projectStatusGuard rejects non-object and wrong keys",()=>{
    expect(bad(projectStatusGuard,null)).toThrow("expected object");
    expect(bad(projectStatusGuard,[])).toThrow("expected object");
    expect(bad(projectStatusGuard,{logicalProjectId:"p",name:"n",targetDevice:"t",extra:1})).toThrow("unexpected object shape");
  });
  it("samplingStatusGuard rejects invalid state enum and wrong field types",()=>{
    expect(bad(samplingStatusGuard,{...validSampling(),state:"UNKNOWN"})).toThrow("unexpected enum");
    expect(bad(samplingStatusGuard,{...validSampling(),active:"yes"})).toThrow("expected boolean");
  });
  it("monitorStatusGuard requires a probe object and rejects a missing firmware type",()=>{
    expect(bad(monitorStatusGuard,{...validStatus(),probe:null})).toThrow("expected object");
    expect(bad(monitorStatusGuard,{...validStatus(),probe:{connected:"yes"}})).toThrow("expected object");
    expect(bad(monitorStatusGuard,{...validStatus(),probeConnected:1})).toThrow("expected boolean");
  });
  it("probeInfoGuard accepts a nullable boardName and rejects a non-string vendor",()=>{
    expect(ok(probeInfoGuard,{probeId:"p",vendor:"ST",product:"L",boardName:null})?.probeId).toBe("p");
    expect(ok(probeInfoGuard,{probeId:"p",vendor:"ST",product:"L",boardName:"B"})?.boardName).toBe("B");
    expect(bad(probeInfoGuard,{probeId:"p",vendor:1,product:"L",boardName:null})).toThrow("expected string");
  });
});

describe("descriptor guards",()=>{
  it("variableDescriptorGuard rejects a non-integer byteSize and requires bounded integer",()=>{
    const base={selector:"x",typeName:"u8",kind:"scalar",signed:false,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]};
    expect(bad(variableDescriptorGuard,{...base,byteSize:"4"})).toThrow("expected integer");
    expect(bad(variableDescriptorGuard,{...base,byteSize:integer("9007199254740993")})).toThrow("outside safe range");
    expect(bad(variableDescriptorGuard,{...base,byteSize:1.5})).toThrow("expected integer");
  });
  it("variableDescriptorGuard guards enum values and nullable element info",()=>{
    const base={selector:"x",typeName:"u8",kind:"scalar",byteSize:integer("1"),signed:false,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]};
    expect(bad(variableDescriptorGuard,{...base,enumValues:[{value:"1",name:"a"}]})).toThrow("expected integer");
    expect(ok(variableDescriptorGuard,{...base,enumValues:[{value:integer("7"),name:"seven"}]})?.enumValues[0]?.value).toBe(7n);
    expect(ok(variableDescriptorGuard,{...base,elementCount:integer("3"),elementKind:"u8"})?.elementCount).toBe(3n);
  });
  it("registerDescriptorGuard requires nonnegative reset values and integer bit fields",()=>{
    const base={selector:"R",sizeBits:integer("32"),access:null,readAction:null,resetValue:null,resetMask:null,fields:[],sampleable:true,requiresAccessAcknowledgement:false};
    expect(bad(registerDescriptorGuard,{...base,resetValue:integer("-1")})).toThrow("nonnegative");
    expect(bad(registerDescriptorGuard,{...base,fields:[{name:"f",bitOffset:"1",bitWidth:2}]})).toThrow("expected integer");
    expect(ok(registerDescriptorGuard,{...base,fields:[{name:"f",bitOffset:integer("1"),bitWidth:integer("2")}]})?.fields[0]?.name).toBe("f");
  });
});

describe("watch guards",()=>{
  it("watchItemGuard accepts variable and register watches and rejects unknown kinds",()=>{
    expect(ok(watchItemGuard,{kind:"variable",expression:"x"})).toEqual({kind:"variable",expression:"x"});
    expect(ok(watchItemGuard,{kind:"register",registerPath:"R"})).toEqual({kind:"register",registerPath:"R"});
    expect(bad(watchItemGuard,{kind:"other"})).toThrow("unknown watch kind");
    expect(bad(watchItemGuard,{kind:"variable"})).toThrow("unexpected object shape");
  });
  it("watchGroupGuard guards group fields",()=>{
    const group=validGroup();
    expect(ok(watchGroupGuard,group)?.revision).toBe(1n);
    expect(bad(watchGroupGuard,{...group,intervalMs:"250"})).toThrow("expected integer");
  });
  it("groupPageGuard accepts nullable cursor and rejects non-array groups",()=>{
    expect(ok(groupPageGuard,{groups:[validGroup()],nextCursor:null,revision:"r"})?.nextCursor).toBeNull();
    expect(bad(groupPageGuard,{groups:{},nextCursor:null,revision:"r"})).toThrow("expected array");
  });
  it("watchGroupsGuard rejects non-array input",()=>{
    expect(bad(watchGroupsGuard,{})).toThrow("expected array");
  });
  it("deletedGroupGuard, releasedGuard, resumedGuard, stoppedGuard reject wrong field shapes",()=>{
    expect(ok(deletedGroupGuard,{groupId:"g",deleted:true})?.deleted).toBe(true);
    expect(bad(deletedGroupGuard,{groupId:"g",deleted:false})).toThrow("unexpected literal");
    expect(ok(releasedGuard,{released:true})?.released).toBe(true);
    expect(bad(releasedGuard,{released:"yes"})).toThrow("expected boolean");
    expect(ok(resumedGuard,{resumed:true})?.resumed).toBe(true);
    expect(ok(stoppedGuard,{stopped:true})?.stopped).toBe(true);
  });
  it("samplerStartGuard rejects a non-integer interval",()=>{
    const value={groupId:"g",groupRevision:integer("1"),runId:"r",intervalMs:"250"};
    expect(bad(samplerStartGuard,value)).toThrow("expected integer");
  });
});

describe("sample guards",()=>{
  it("sampleValueGuard accepts OK and ERROR samples and rejects inconsistent ones",()=>{
    const base={watch:{kind:"variable",expression:"x"},typedValue:1,code:null,definition:null};
    expect(ok(sampleValueGuard,{...base,status:"OK"})?.status).toBe("OK");
    expect(ok(sampleValueGuard,{...base,status:"OK",typedValue:null})?.status).toBe("OK");
    expect(bad(sampleValueGuard,{...base,status:"OK",code:"X"})).toThrow("OK sample has code");
    expect(ok(sampleValueGuard,{...base,status:"ERROR",typedValue:null,code:"BAD"})?.code).toBe("BAD");
    expect(bad(sampleValueGuard,{...base,status:"ERROR",typedValue:1,code:"BAD"})).toThrow("ERROR sample has value");
    expect(bad(sampleValueGuard,{...base,status:"NOPE"})).toThrow("unknown sample status");
  });
  it("sampleValueGuard guards definition as a JSON record",()=>{
    const base={watch:{kind:"variable",expression:"x"},status:"OK",typedValue:1,code:null};
    const withDef=ok(sampleValueGuard,{...base,definition:{n:1}});
    expect(withDef?.definition).toEqual({n:1});
    expect(bad(sampleValueGuard,{...base,definition:1})).toThrow("expected object");
  });
});

describe("live event guard",()=>{
  it("accepts all four event kinds",()=>{
    expect(ok(liveEventGuard,helloEvent())?.type).toBe("hello");
    expect(ok(liveEventGuard,stateEvent())?.type).toBe("state");
    expect(ok(liveEventGuard,sampleEvent())?.type).toBe("sample");
    expect(ok(liveEventGuard,heartbeatEvent())?.type).toBe("heartbeat");
  });
  it("rejects an unknown live event type",()=>{
    expect(bad(liveEventGuard,{eventId:integer("1"),type:"bogus",data:{}})).toThrow("unknown live event");
  });
  it("rejects an invalid hello protocol",()=>{
    const event=helloEvent();
    event.data.protocol="wrong";
    expect(bad(liveEventGuard,event)).toThrow("unexpected literal");
  });
  it("rejects a state event whose status is malformed",()=>{
    const event=stateEvent();
    (event.data as {status:unknown}).status={bad:true};
    expect(bad(liveEventGuard,event)).toThrow();
  });
});

describe("envelope parsing",()=>{
  const header={protocol:"stm32-toolkit-monitor/1",toolkitVersion:"v",monitorVersion:"v",operation:"monitor.test",details:{}};
  it("parseEnvelope returns MONITOR_RESPONSE_INVALID on malformed input",()=>{
    expect(parseEnvelope("not-json","monitor.test",()=>null)).toEqual({ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"});
  });
  it("parseEnvelope rejects an operation mismatch",()=>{
    const text=(body:string)=>JSON.stringify({...header,ok:true,code:"OK",message:"",data:body});
    expect(parseEnvelope(text("null"),"monitor.other",()=>null)).toEqual({ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"});
  });
  it("parseEnvelope accepts a success envelope and exposes details",()=>{
    const envelope=JSON.stringify({...header,ok:true,code:"OK",message:"",data:42,details:{subscriberDropped:1}});
    const result=parseEnvelope(envelope,"monitor.test",()=>42);
    expect(result).toEqual({ok:true,data:42});
    expect(envelopeDetails(result)).toEqual({subscriberDropped:new IntegerToken("1")});
  });
  it("parseEnvelopeText forwards to parseEnvelope",()=>{
    const envelope=JSON.stringify({...header,ok:true,code:"OK",message:"",data:1,details:{}});
    expect(parseEnvelopeText(envelope,"monitor.test",()=>1)).toEqual({ok:true,data:1});
  });
  it("parseEnvelope accepts a failure envelope with inconsistent markers rejected",()=>{
    const envelope=JSON.stringify({...header,ok:false,code:"ERR",message:"failed",data:null,details:{}});
    expect(parseEnvelope(envelope,"monitor.test",()=>null)).toEqual({ok:false,code:"ERR",message:"failed"});
    const inconsistent=JSON.stringify({...header,ok:false,code:"OK",message:"",data:null,details:{}});
    expect(parseEnvelope(inconsistent,"monitor.test",()=>null)).toEqual({ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"});
  });
  it("parseEnvelope guards the data field through the provided guard",()=>{
    const envelope=JSON.stringify({...header,ok:true,code:"OK",message:"",data:{bad:true},details:{}});
    const result=parseEnvelope(envelope,"monitor.test",()=>{throw new Error("guard failed");});
    expect(result).toEqual({ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"});
  });
});

describe("artifacts and pages",()=>{
  it("exportArtifactGuard accepts csv/jsonl and rejects other formats",()=>{
    expect(ok(exportArtifactGuard,{exportId:"e",format:"jsonl",sha256:"s",bytes:integer("1"),valueCount:integer("2")})?.format).toBe("jsonl");
    expect(bad(exportArtifactGuard,{exportId:"e",format:"xml",sha256:"s",bytes:integer("1"),valueCount:integer("2")})).toThrow("unexpected enum");
  });
  it("historyBatchSliceGuard and historyPageGuard accept valid pages",()=>{
    const batch=batchSlice();
    expect(ok(historyBatchSliceGuard,batch)?.startOrdinal).toBe(1n);
    const page={batches:[batch],valueCount:integer("1"),nextCursor:null,serializedBytes:integer("2")};
    expect(ok(historyPageGuard,page)?.nextCursor).toBeNull();
    expect(ok(historyPageGuard,{...page,nextCursor:"c"})?.nextCursor).toBe("c");
  });
});

function validSampling(){return {state:"IDLE",active:false,blockedCode:null,groupId:null,groupRevision:null,runId:null,lastSequence:null,bindingEpoch:integer("0"),subscriberDrops:integer("0"),historyDrops:integer("0"),deadlineDrops:integer("0"),serviceDrops:integer("0")};}
function validStatus(){return {workspaceId:"w",sessionId:"s",project:{logicalProjectId:"p",name:"n",targetDevice:"t"},firmware:null,probe:{connected:false,probeId:null},sampling:validSampling(),probeConnected:false,samplingActive:false};}
function validGroup(){return {groupId:"g",name:"n",description:"d",intervalMs:integer("250"),items:[{kind:"variable",expression:"x"}],revision:integer("1"),createdAtUtc:"c",updatedAtUtc:"u"};}
function helloEvent(){return {eventId:integer("1"),type:"hello",data:{protocol:"stm32-toolkit-monitor/1",toolkitVersion:"v",monitorVersion:"v",stateRevision:integer("1")}};}
function stateEvent(){return {eventId:integer("1"),type:"state",data:{stateRevision:integer("1"),gap:false,status:validStatus()}};}
function sampleEvent(){return {eventId:integer("1"),type:"sample",data:{batch:{binding:observationBinding(),groupId:"g",groupRevision:integer("1"),runId:"r",sequence:integer("1"),scheduledUnixNs:integer("1"),scheduledAtUtc:"s",capturedUnixNs:integer("1"),capturedAtUtc:"c",latencyNs:integer("0"),actualRateHz:1,subscriberDrops:integer("0"),historyDrops:integer("0"),deadlineDrops:integer("0"),values:[]},serviceSubscriberDrops:integer("0")}};}
function heartbeatEvent(){return {eventId:integer("1"),type:"heartbeat",data:{stateRevision:integer("1"),capturedAtUtc:"c"}};}
function observationBinding(){return {workspaceId:"w",logicalProjectId:"p",sessionId:"s",probeId:"p",targetDevice:"t",physicalTarget:"t",buildId:"b",elfSha256:"e",inputSnapshotSha256:"i",gitHead:"h",gitDirty:false,flashSessionId:"f",leaseId:"l",dwarfSha256:"d",svdSha256:null};}
function batchSlice(){return {binding:observationBinding(),groupId:"g",groupRevision:integer("1"),runId:"r",sequence:integer("1"),scheduledUnixNs:integer("1"),scheduledAtUtc:"s",capturedUnixNs:integer("1"),capturedAtUtc:"c",latencyNs:integer("0"),actualRateHz:1,subscriberDrops:integer("0"),historyDrops:integer("0"),deadlineDrops:integer("0"),values:[],startOrdinal:integer("1"),batchValueCount:integer("0")};}
