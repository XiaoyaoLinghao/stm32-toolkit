import {describe,expect,it} from "vitest";
import {createController} from "../src/controller";
import type {MonitorApi,MonitorStatus,SourceCatalogItem,SourceCatalogPage} from "../src/api/contract";
import {initialState,reducer} from "../src/state/reducer";
import {sourceContextKey,type MonitorAction,type MonitorState} from "../src/state/model";
import {recordingApi,sourcePage,statusResult} from "./fixtures";

const item:SourceCatalogItem={id:"c".repeat(64),parentId:null,name:"counter",typeName:"int",file:"Src/main.c",line:1,column:5,
  scope:{kind:"global",function:null,path:[]},storage:"none",translationUnits:["Src/main.c"],selector:"counter",
  canAdd:true,reason:null,expandable:false,truncated:false};
const connected=():MonitorStatus=>{const base=statusResult();return{...base,probe:{connected:true,probeId:"probe"},probeConnected:true,
  firmware:{buildId:"build",elfSha256:"e".repeat(64),inputSnapshotSha256:"b".repeat(64),gitHead:"g".repeat(40),gitDirty:false,targetDevice:base.project.targetDevice}};};
const page=(status:MonitorStatus):SourceCatalogPage=>({...sourcePage(status),total:1,items:[item]});
const loaded=(status:MonitorStatus)=>{
  let state=reducer(initialState,{type:"initial.loaded",status,probes:[],groups:[]});
  const contextKey=sourceContextKey(status);
  state=reducer(state,{type:"source.started",query:"",contextKey});
  state=reducer(state,{type:"source.loaded",query:"",contextKey,generation:state.catalog.source.generation,
    cursor:null,parentId:null,page:page(status)});
  return state;
};

describe("source catalog adoption lifecycle",()=>{
  it("keeps source browsing when disconnected and rejects a late same-epoch page and selection",()=>{
    const status=connected(),original=loaded(status),contextKey=sourceContextKey(status),generation=original.catalog.source.generation;
    const disconnected={...status,probe:{connected:false,probeId:null},probeConnected:false};
    let state=reducer(original,{type:"status.loaded",status:disconnected});
    expect(state.catalog.source.page).toBeNull();
    state=reducer(state,{type:"source.loaded",query:"",contextKey,generation,cursor:null,parentId:null,page:page(status)});
    state=reducer(state,{type:"source.selection.accepted",contextKey,generation,groupGeneration:original.groupGeneration,
      catalogId:page(status).catalogId,itemId:item.id,selector:"counter",watch:{kind:"variable",expression:"counter"}});
    expect(state.catalog.source.page).toBeNull();
    expect(state.groupDraft.items).toEqual([]);
    expect(state.status?.sampling.bindingEpoch).toBe(0n);
  });

  it("retires a same-epoch firmware change and an old query or child page",()=>{
    const status=connected(),old=loaded(status),contextKey=sourceContextKey(status),generation=old.catalog.source.generation;
    const firmware={...status.firmware!,buildId:"next"};
    let state=reducer(old,{type:"status.loaded",status:{...status,firmware}});
    expect(state.catalog.source.page).toBeNull();
    state=reducer(state,{type:"source.loaded",query:"",contextKey,generation,cursor:null,parentId:null,page:page(status)});
    expect(state.catalog.source.page).toBeNull();
    state=reducer(state,{type:"source.started",query:"gpio",contextKey:sourceContextKey(state.status!)});
    expect(state.catalog.source.generation).toBeGreaterThan(generation);
    state=reducer(state,{type:"source.loaded",query:"",contextKey,generation,cursor:null,parentId:null,page:page(status)});
    expect(state.catalog.source.page).toBeNull();
  });

  it("keeps a fresh readonly source page when status firmware lags, without enabling Add",()=>{
    const status=connected(),contextKey=sourceContextKey(status);
    let state=reducer(initialState,{type:"initial.loaded",status,probes:[],groups:[]});
    state=reducer(state,{type:"source.started",query:"",contextKey});
    const fresh={...page(status),identity:{...page(status).identity,buildId:"new-build",elfSha256:"f".repeat(64)}};
    state=reducer(state,{type:"source.loaded",query:"",contextKey,generation:state.catalog.source.generation,
      cursor:null,parentId:null,page:fresh});
    expect(state.catalog.source.page?.items[0]?.canAdd).toBe(false);
    expect(state.catalog.source.page?.items[0]?.reason).toBe("source_mismatch");
    state=reducer(state,{type:"source.selection.accepted",contextKey,generation:state.catalog.source.generation,
      groupGeneration:state.groupGeneration,catalogId:fresh.catalogId,itemId:item.id,selector:"counter",
      watch:{kind:"variable",expression:"counter"}});
    expect(state.groupDraft.items).toEqual([]);
  });

  it("requires the original group generation when an async selection ACK arrives",async()=>{
    const status=connected();let state:MonitorState=loaded(status);
    let resolve!:(result:Awaited<ReturnType<MonitorApi["sourceSelection"]>>)=>void;
    const pending=new Promise<Awaited<ReturnType<MonitorApi["sourceSelection"]>>>(done=>{resolve=done;});
    const api:MonitorApi={...recordingApi([],status),sourceSelection:()=>pending};
    const dispatch=(action:MonitorAction)=>{state=reducer(state,action);};
    const controller=createController(api,dispatch,()=>state);
    const selecting=controller.selectSource(item);
    expect(state.pending["catalog.source-selection"]).toBeDefined();
    state=reducer(state,{type:"group.navigation.requested",target:{kind:"new"}});
    resolve({ok:true,data:{catalogId:page(status).catalogId,item:{kind:"variable",expression:"counter"}}});
    await selecting;
    expect(state.groupDraft.items).toEqual([]);
    expect(state.catalog.source.lastAddedId).toBeNull();
    controller.close();
  });

  it("adds a validated current leaf only to the active draft",()=>{
    const status=connected(),contextKey=sourceContextKey(status);
    let state=loaded(status);
    state=reducer(state,{type:"source.selection.accepted",contextKey,generation:state.catalog.source.generation,
      groupGeneration:state.groupGeneration,catalogId:page(status).catalogId,itemId:item.id,selector:"counter",
      watch:{kind:"variable",expression:"counter"}});
    expect(state.groupDraft.items).toEqual([{kind:"variable",expression:"counter"}]);
    expect(state.catalog.source.lastAddedId).toBe(item.id);
    const again=reducer(state,{type:"source.selection.accepted",contextKey,generation:state.catalog.source.generation,
      groupGeneration:state.groupGeneration,catalogId:page(status).catalogId,itemId:item.id,selector:"counter",
      watch:{kind:"variable",expression:"counter"}});
    expect(again).toBe(state);
  });
});
