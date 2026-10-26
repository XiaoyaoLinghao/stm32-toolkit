import {describe,expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import type {FirmwareStatus,GitEvidenceUnavailable,MonitorStatus,ObservationBinding,SampleBatch} from "../src/api/contract";
import {debugFirmwareBindingGuard,firmwareStatusGuard,historyPageGuard,monitorStatusGuard,observationBindingGuard,parseEnvelope} from "../src/api/contract";
import {parseLiveEnvelope} from "../src/api/live";
import {IdentityBar} from "../src/components/IdentityBar";
import {initialState,reduceAcceptedLiveEnvelope,reducer} from "../src/state/reducer";
import {sourceContextKey} from "../src/state/model";
import {sourceTreePage,statusResult,watchGroup} from "./fixtures";

const SNAPSHOT="input-snapshot-v1" as const;
const HEAD_EVIDENCE={status:"unavailable",code:"BUILD_GIT_INVALID",rule:"head"} as const;
const STATUS_EVIDENCE={status:"unavailable",code:"BUILD_GIT_INVALID",rule:"status"} as const;
const PROJECT={logicalProjectId:"project",name:"Project",targetDevice:"STM32F407VGTx"};
const INVALID={ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"};

const legacyFirmwareDoc=()=>({buildId:"b".repeat(64),elfSha256:"e".repeat(64),inputSnapshotSha256:"f".repeat(64),gitHead:"a".repeat(40),gitDirty:false,targetDevice:PROJECT.targetDevice});
const snapshotFirmwareDoc=()=>({...legacyFirmwareDoc(),inputSnapshotSha256:"9".repeat(64),gitHead:null,gitDirty:null,sourceBaseline:SNAPSHOT,gitEvidence:{...HEAD_EVIDENCE}});
const legacyBindingDoc=()=>({workspaceId:"workspace",logicalProjectId:PROJECT.logicalProjectId,sessionId:"session",probeId:"probe",targetDevice:PROJECT.targetDevice,physicalTarget:"stm32f407vg",buildId:"b".repeat(64),elfSha256:"e".repeat(64),inputSnapshotSha256:"f".repeat(64),gitHead:"a".repeat(40),gitDirty:false,flashSessionId:"flash",leaseId:"lease",dwarfSha256:"d".repeat(64),svdSha256:null});
const snapshotBindingDoc=()=>({...legacyBindingDoc(),inputSnapshotSha256:"9".repeat(64),gitHead:null,gitDirty:null,sourceBaseline:SNAPSHOT,gitEvidence:{...HEAD_EVIDENCE}});
const debugBindingDoc=(snapshot=true)=>({
  logicalProjectId:PROJECT.logicalProjectId,workspaceId:"workspace",observationSessionId:"session",flashSessionId:"flash",leaseId:"lease",
  probeId:"probe",targetDevice:PROJECT.targetDevice,debugTarget:"stm32f407vg",buildId:"b".repeat(64),elfSha256:"e".repeat(64),
  elfSize:4096,elfPath:"build/firmware.elf",inputSnapshotSha256:snapshot?"9".repeat(64):"f".repeat(64),
  gitHead:snapshot?null:"a".repeat(40),gitDirty:snapshot?null:false,confirmedAtUtc:"2026-08-08T01:02:03.000000Z",
  memoryRegions:[{name:"FLASH",origin:0x08000000,length:1024,attributes:"r-x"}],
  svdReadableRegions:[{name:"PERIPH",origin:0x40000000,length:0x1000,attributes:"r--"}],
  ...(snapshot?{sourceBaseline:SNAPSHOT,gitEvidence:{...HEAD_EVIDENCE}}:{}),
});

const wireStatus=(firmware:unknown)=>({workspaceId:"workspace",sessionId:"session",project:PROJECT,firmware,
  probe:{connected:true,probeId:"probe"},sampling:{state:"RUNNING",active:true,blockedCode:null,groupId:"group",
  groupRevision:1,runId:"run",lastSequence:null,bindingEpoch:4,subscriberDrops:0,historyDrops:0,deadlineDrops:0,serviceDrops:0},
  probeConnected:true,samplingActive:true});
const historyWire=(binding:unknown)=>({batches:[{binding,groupId:"group",groupRevision:1,runId:"run",sequence:0,
  scheduledUnixNs:1,scheduledAtUtc:"2026-08-10T00:00:00Z",capturedUnixNs:2,capturedAtUtc:"2026-08-10T00:00:00Z",latencyNs:1,
  actualRateHz:4,subscriberDrops:0,historyDrops:0,deadlineDrops:0,values:[],startOrdinal:0,batchValueCount:0}],
  valueCount:0,nextCursor:null,serializedBytes:0});
const sampleWire=(binding:unknown)=>({eventId:1,type:"sample",data:{batch:{binding,groupId:"group",groupRevision:1,runId:"run",
  sequence:0,scheduledUnixNs:1,scheduledAtUtc:"2026-08-10T00:00:00Z",capturedUnixNs:2,capturedAtUtc:"2026-08-10T00:00:00Z",latencyNs:1,
  actualRateHz:4,subscriberDrops:0,historyDrops:0,deadlineDrops:0,values:[]},serviceSubscriberDrops:0}});
const okEnvelope=(operation:string,data:unknown,details:unknown={})=>JSON.stringify({protocol:"stm32-toolkit-monitor/1",
  toolkitVersion:"1.3.2",monitorVersion:"1.3.2",ok:true,operation,code:"OK",message:"",data,details});

const snapshotStatus=(overrides:{inputSnapshotSha256?:string;gitEvidence?:GitEvidenceUnavailable}={}):MonitorStatus=>{
  const base=statusResult();
  return {...base,project:{...base.project,targetDevice:PROJECT.targetDevice},probe:{connected:true,probeId:"probe"},probeConnected:true,
    sampling:{...base.sampling,state:"RUNNING",active:true,runId:"run",groupId:"group",groupRevision:1n,bindingEpoch:4n},
    firmware:{buildId:"b".repeat(64),elfSha256:"e".repeat(64),inputSnapshotSha256:overrides.inputSnapshotSha256??"9".repeat(64),
      gitHead:null,gitDirty:null,targetDevice:PROJECT.targetDevice,sourceBaseline:SNAPSHOT,gitEvidence:overrides.gitEvidence??{...HEAD_EVIDENCE}}};
};
const snapshotBinding=():ObservationBinding=>observationBindingGuard(snapshotBindingDoc());
const sample=(binding:ObservationBinding):SampleBatch=>({binding,groupId:"group",groupRevision:1n,runId:"run",sequence:1n,
  scheduledUnixNs:1n,scheduledAtUtc:"2026-08-10T00:00:00Z",capturedUnixNs:2n,capturedAtUtc:"2026-08-10T00:00:00Z",latencyNs:1n,
  actualRateHz:4,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,
  values:[{watch:{kind:"variable",expression:"counter"},status:"OK",typedValue:{expression:"counter",typeName:"int",value:7,rawHex:"0x7",bitWidth:32},code:null,definition:null}]});

describe("snapshot provenance contract",()=>{
  it("accepts snapshot status, debug binding, observation binding and history through public parsers",()=>{
    const status=parseEnvelope(okEnvelope("monitor.status",wireStatus(snapshotFirmwareDoc())),"monitor.status",monitorStatusGuard);
    expect(status.ok).toBe(true);
    if(status.ok){
      const firmware=status.data.firmware;
      expect(firmware).not.toBeNull();
      if(firmware!==null&&firmware.gitHead===null){
        expect(firmware.gitDirty).toBeNull();
        expect(firmware.sourceBaseline).toBe(SNAPSHOT);
        expect(firmware.gitEvidence).toEqual(HEAD_EVIDENCE);
      }else throw new Error("expected snapshot firmware");
    }
    const debug=parseEnvelope(okEnvelope("monitor.probe.connect",debugBindingDoc()),"monitor.probe.connect",debugFirmwareBindingGuard);
    expect(debug.ok).toBe(true);
    if(debug.ok){
      expect(debug.data.gitHead).toBeNull();
      if(debug.data.gitHead===null)expect(debug.data.gitEvidence).toEqual(HEAD_EVIDENCE);
    }
    const observation=snapshotBinding();
    expect(observation.gitHead).toBeNull();
    if(observation.gitHead===null)expect(observation.sourceBaseline).toBe(SNAPSHOT);
    const live=parseLiveEnvelope(okEnvelope("monitor.live",sampleWire(snapshotBindingDoc()),{subscriberDropped:0}));
    expect(live.ok).toBe(true);
    if(live.ok&&live.data.event.type==="sample"){
      const binding=live.data.event.data.batch.binding;
      expect(binding.gitHead).toBeNull();
      if(binding.gitHead===null)expect(binding.gitEvidence).toEqual(HEAD_EVIDENCE);
    }
    const history=parseEnvelope(okEnvelope("monitor.history.query",historyWire(snapshotBindingDoc())),"monitor.history.query",historyPageGuard);
    expect(history.ok).toBe(true);
    if(history.ok){
      const binding=history.data.batches[0]?.binding;
      expect(binding?.gitHead).toBeNull();
      if(binding!==undefined&&binding.gitHead===null)expect(binding.gitEvidence).toEqual(HEAD_EVIDENCE);
    }
  });

  it("rejects partial, present-null, unknown, mixed and extra provenance fields",()=>{
    const legacy=legacyFirmwareDoc(),snapshot=snapshotFirmwareDoc();
    const firmwareCases:unknown[]=[
      {...legacy,sourceBaseline:SNAPSHOT},
      {...legacy,gitEvidence:{...HEAD_EVIDENCE}},
      {...legacy,sourceBaseline:null,gitEvidence:null},
      {...legacy,gitHead:null},
      {...snapshot,gitHead:"a".repeat(40)},
      {...snapshot,gitDirty:false},
      {...snapshot,sourceBaseline:null},
      {...snapshot,sourceBaseline:"git"},
      {...snapshot,gitEvidence:null},
      {...snapshot,gitEvidence:{...HEAD_EVIDENCE,rule:"branch"}},
      {...snapshot,gitEvidence:{...HEAD_EVIDENCE,extra:true}},
      {...snapshot,extra:true},
    ];
    for(const doc of firmwareCases){
      expect(()=>firmwareStatusGuard(doc)).toThrow();
      expect(parseEnvelope(okEnvelope("monitor.status",wireStatus(doc)),"monitor.status",monitorStatusGuard)).toEqual(INVALID);
    }

    const partialDebug:Record<string,unknown>={...debugBindingDoc()};delete partialDebug.gitEvidence;
    const debugCases:unknown[]=[partialDebug,{...debugBindingDoc(),sourceBaseline:null},
      {...debugBindingDoc(),gitHead:"a".repeat(40),gitDirty:false},
      {...debugBindingDoc(),gitEvidence:{...HEAD_EVIDENCE,code:"OTHER"}},{...debugBindingDoc(),extra:true}];
    for(const doc of debugCases){
      expect(()=>debugFirmwareBindingGuard(doc)).toThrow();
      expect(parseEnvelope(okEnvelope("monitor.probe.connect",doc),"monitor.probe.connect",debugFirmwareBindingGuard)).toEqual(INVALID);
    }

    const partialObservation:Record<string,unknown>={...snapshotBindingDoc()};delete partialObservation.sourceBaseline;
    const observationCases:unknown[]=[partialObservation,{...snapshotBindingDoc(),gitHead:"a".repeat(40)},
      {...snapshotBindingDoc(),gitEvidence:{...STATUS_EVIDENCE,status:"available"}},
      {...snapshotBindingDoc(),gitEvidence:{...HEAD_EVIDENCE,extra:true}},{...snapshotBindingDoc(),extra:true}];
    for(const doc of observationCases){
      expect(()=>observationBindingGuard(doc)).toThrow();
      expect(parseEnvelope(okEnvelope("monitor.history.query",historyWire(doc)),"monitor.history.query",historyPageGuard)).toEqual(INVALID);
    }
    expect(parseLiveEnvelope(okEnvelope("monitor.live",sampleWire({...snapshotBindingDoc(),gitEvidence:null}),{subscriberDropped:0}))).toEqual(INVALID);
  });

  it("shows the input snapshot and an honest Git-unavailable label for snapshot firmware",()=>{
    const parsed=parseEnvelope(okEnvelope("monitor.status",wireStatus(snapshotFirmwareDoc())),"monitor.status",monitorStatusGuard);
    if(!parsed.ok||parsed.data.firmware===null)throw new Error("expected snapshot status");
    render(<IdentityBar project={parsed.data.project} firmware={parsed.data.firmware} onCopy={vi.fn()}/>);
    expect(screen.getByText("9".repeat(64))).toBeTruthy();
    expect(screen.getByText(/输入快照/)).toBeTruthy();
    expect(screen.getByText(/Git 不可用/)).toBeTruthy();
    expect(screen.queryByText("a".repeat(40))).toBeNull();
  });

  it("preserves the legacy Git display and canonical contract",()=>{
    const legacy=legacyFirmwareDoc();
    const firmware:FirmwareStatus=firmwareStatusGuard(legacy);
    expect(firmware).toEqual(legacy);
    expect(firmware.gitHead).toBe("a".repeat(40));
    expect(firmware.gitDirty).toBe(false);
    render(<IdentityBar project={PROJECT} firmware={firmware} onCopy={vi.fn()}/>);
    expect(screen.getByText("a".repeat(40))).toBeTruthy();
    expect(screen.queryByText(/输入快照/)).toBeNull();
    expect(screen.queryByText(/Git 不可用/)).toBeNull();
    expect(parseEnvelope(okEnvelope("monitor.status",wireStatus(legacy)),"monitor.status",monitorStatusGuard).ok).toBe(true);
    expect(parseEnvelope(okEnvelope("monitor.probe.connect",debugBindingDoc(false)),"monitor.probe.connect",debugFirmwareBindingGuard).ok).toBe(true);
    expect(parseEnvelope(okEnvelope("monitor.history.query",historyWire(legacyBindingDoc())),"monitor.history.query",historyPageGuard).ok).toBe(true);
  });
});

describe("provenance pair in reducer identity",()=>{
  const seeded=()=>{
    const status=snapshotStatus();
    let state=reducer(initialState,{type:"initial.loaded",status,probes:[],groups:[watchGroup()]});
    const contextKey=sourceContextKey(status);
    state=reducer(state,{type:"source.started",query:"",contextKey,generation:state.catalog.source.generation+1n});
    state=reducer(state,{type:"source.tree.loaded",query:"",contextKey,generation:state.catalog.source.generation,parentId:null,page:sourceTreePage(status)});
    return reduceAcceptedLiveEnvelope(state,{event:{eventId:1n,type:"sample",data:{batch:sample(snapshotBinding()),serviceSubscriberDrops:0n}},subscriberDropped:0n});
  };

  it("keys source context on canonical pair scalars, not object insertion order",()=>{
    const reordered:GitEvidenceUnavailable={rule:"head",code:"BUILD_GIT_INVALID",status:"unavailable"};
    expect(sourceContextKey(snapshotStatus({gitEvidence:reordered}))).toBe(sourceContextKey(snapshotStatus()));
    expect(sourceContextKey(snapshotStatus({gitEvidence:{...STATUS_EVIDENCE}}))).not.toBe(sourceContextKey(snapshotStatus()));
    expect(sourceContextKey(snapshotStatus({inputSnapshotSha256:"8".repeat(64)}))).not.toBe(sourceContextKey(snapshotStatus()));
  });

  it("keeps cached source and live state for equivalent evidence but invalidates on a changed pair",()=>{
    const state=seeded();
    expect(state.live.rows.size).toBeGreaterThan(0);
    expect(state.catalog.source.initialized).toBe(true);
    const equivalent=reducer(state,{type:"status.loaded",status:snapshotStatus({gitEvidence:{rule:"head",code:"BUILD_GIT_INVALID",status:"unavailable"}})});
    expect(sourceContextKey(equivalent.status!)).toBe(sourceContextKey(state.status!));
    expect(equivalent.live.rows.size).toBe(state.live.rows.size);
    expect(equivalent.catalog.source.initialized).toBe(true);
    const changed=reducer(equivalent,{type:"status.loaded",status:snapshotStatus({gitEvidence:{...STATUS_EVIDENCE}})});
    expect(sourceContextKey(changed.status!)).not.toBe(sourceContextKey(equivalent.status!));
    expect(changed.live.rows.size).toBe(0);
    expect(changed.catalog.source.initialized).toBe(false);
    expect(changed.catalog.source.tree).toBeNull();
  });

  it("invalidates cached source and live state when the input snapshot digest changes",()=>{
    const state=seeded();
    const changed=reducer(state,{type:"status.loaded",status:snapshotStatus({inputSnapshotSha256:"8".repeat(64)})});
    expect(sourceContextKey(changed.status!)).not.toBe(sourceContextKey(state.status!));
    expect(changed.live.rows.size).toBe(0);
    expect(changed.catalog.source.initialized).toBe(false);
  });

  it("rejects a live sample whose binding carries a different provenance pair",()=>{
    const state=seeded();
    const changedBinding=observationBindingGuard({...snapshotBindingDoc(),gitEvidence:{...STATUS_EVIDENCE}});
    const next=reduceAcceptedLiveEnvelope(state,{event:{eventId:2n,type:"sample",data:{batch:sample(changedBinding),serviceSubscriberDrops:0n}},subscriberDropped:0n});
    expect(next.transport.stale).toBe(true);
    expect(next.live.rows.size).toBe(state.live.rows.size);
    expect(next.live.binding).toBe(state.live.binding);
  });
});
