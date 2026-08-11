import {expect,it} from "vitest";
import type {VariableDescriptor} from "../src/api/contract";
import {deriveElement,deriveMember} from "../src/catalog/shallow-selectors";
import {initialState,reducer} from "../src/state/reducer";

const descriptor:VariableDescriptor={selector:"state",typeName:"State",kind:"structure",byteSize:8,signed:null,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:3n,elementKind:"u8",memberNames:["rpm"]};
it("never accepts a catalog page for an obsolete binding cursor",()=>{
  const base={...initialState,status:{workspaceId:"w",sessionId:"s",project:{logicalProjectId:"p",name:"p",targetDevice:"t"},firmware:null,probe:{connected:true,probeId:"p"},sampling:{state:"IDLE" as const,active:false,blockedCode:null,groupId:null,groupRevision:null,runId:null,lastSequence:null,bindingEpoch:4n,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n},probeConnected:true,samplingActive:false}};
  const requested=reducer(base,{type:"catalog.requested",catalog:"variables",query:"x",bindingKey:"w/s/p/4",cursor:null});
  const rebound={...requested,status:{...requested.status!,sampling:{...requested.status!.sampling,bindingEpoch:5n}}};
  expect(reducer(rebound,{type:"catalog.loaded",catalog:"variables",query:"x",bindingKey:"w/s/p/4",cursor:null,items:[],nextCursor:"old"})).toEqual(rebound);
});
it("derives only declared one-hop members and valid bounded elements",()=>{
  expect(deriveMember(descriptor,"rpm")).toEqual({kind:"variable",expression:"state.rpm"});
  expect(deriveMember(descriptor,"missing")).toBeNull();
  expect(deriveElement(descriptor,2)).toEqual({kind:"variable",expression:"state[2]"});
  expect(deriveElement(descriptor,3)).toBeNull();
  expect(deriveElement(descriptor,1.5)).toBeNull();
});
