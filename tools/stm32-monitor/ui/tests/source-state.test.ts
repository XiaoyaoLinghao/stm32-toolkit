import {describe,expect,it,vi} from "vitest";
import {createController} from "../src/controller";
import type {MonitorApi,MonitorStatus,SourceCatalogItem,SourceFileNode,SourceScopeNode,SourceTreePage} from "../src/api/contract";
import {initialState,reducer} from "../src/state/reducer";
import {sourceContextKey,type MonitorAction,type MonitorState} from "../src/state/model";
import {recordingApi,sourcePage,sourceTreePage,statusResult} from "./fixtures";

const file=(letter:string,name:string):SourceFileNode=>({kind:"file",id:letter.repeat(64),parentId:null,
 file:`Src/${name}`,name,scopeCount:1,variableCount:1});
const main=file("1","main.c"),safe=file("2","safe.c");
const scope=(letter:string,parent:SourceFileNode):SourceScopeNode=>({kind:"scope",id:letter.repeat(64),
 parentId:parent.id,file:parent.file,name:"global",function:null,line:null,variableCount:1});
const mainScope=scope("3",main),safeScope=scope("4",safe);
const item:SourceCatalogItem={id:"c".repeat(64),parentId:null,name:"counter",typeName:"int",file:main.file,line:1,column:5,
 scope:{kind:"global",function:null,path:[]},storage:"none",translationUnits:[main.file],selector:"counter",
 canAdd:true,reason:null,expandable:false,truncated:false};
const connected=():MonitorStatus=>{const base=statusResult();return{...base,probe:{connected:true,probeId:"probe"},probeConnected:true,
 firmware:{buildId:"build",elfSha256:"e".repeat(64),inputSnapshotSha256:"b".repeat(64),gitHead:"g".repeat(40),gitDirty:false,targetDevice:base.project.targetDevice}};};
const tree=(status:MonitorStatus,files:readonly SourceFileNode[]=[main]):SourceTreePage=>({...sourceTreePage(status),total:files.length,items:files});
const loaded=(status:MonitorStatus):MonitorState=>{
 let state=reducer(initialState,{type:"initial.loaded",status,probes:[],groups:[]});
 const contextKey=sourceContextKey(status);
 state=reducer(state,{type:"source.started",query:"",contextKey,generation:state.catalog.source.generation+1n});
 state=reducer(state,{type:"source.tree.loaded",query:"",contextKey,generation:state.catalog.source.generation,parentId:null,page:tree(status)});
 state=reducer(state,{type:"source.tree.loaded",query:"",contextKey,generation:state.catalog.source.generation,parentId:main.id,
  page:{...tree(status),total:1,items:[mainScope]}});
 state=reducer(state,{type:"source.variables.loaded",query:"",contextKey,generation:state.catalog.source.generation,
  cursor:null,parentId:null,scopeId:mainScope.id,page:{...sourcePage(status),total:1,items:[item]}});
 return state;
};

describe("source tree lifecycle",()=>{
 it("rejects inconsistent directory pages before publishing a new result",async()=>{
  const status=connected();
  const cases:[string,(cursor:string|undefined)=>SourceTreePage][]=[
   ["duplicate file",()=>({...tree(status,[main,main]),total:2})],
   ["incomplete final page",()=>({...tree(status,[main]),total:2})],
   ["repeated cursor",cursor=>cursor===undefined?{...tree(status,[main]),total:2,nextCursor:"again"}:
    {...tree(status,[safe]),total:2,nextCursor:"again"}],
   ["changed catalog identity",cursor=>cursor===undefined?{...tree(status,[main]),total:2,nextCursor:"again"}:
    {...tree(status,[safe]),catalogId:"f".repeat(64),total:2}],
   ["different workspace",()=>({...tree(status,[main]),identity:{...tree(status).identity,workspaceId:"other"}})],
  ];
  for(const [name,page] of cases){
   let state:MonitorState=reducer(initialState,{type:"initial.loaded",status,probes:[],groups:[]});
   const api:MonitorApi={...recordingApi([],status),sourceTree:async(_query,cursor)=>({ok:true,data:page(cursor)})};
   const controller=createController(api,action=>{state=reducer(state,action);},()=>state);
   try{
    await controller.searchSource(name);
    expect(state.failures["catalog.source"]?.code,name).toBe("MONITOR_RESPONSE_INVALID");
    expect(state.catalog.source.tree,name).toBeNull();
   }finally{controller.close();}
  }
 });

 it("loads only requested member pages and refuses a selection absent from the current page",async()=>{
  const status=connected();let state=loaded(status);
  const aggregate:SourceCatalogItem={...item,id:"d".repeat(64),name:"samples",selector:null,canAdd:false,expandable:true};
  const contextKey=sourceContextKey(status),generation=state.catalog.source.generation;
  state=reducer(state,{type:"source.variables.loaded",query:"",contextKey,generation,cursor:null,
   parentId:null,scopeId:mainScope.id,page:{...sourcePage(status),total:1,items:[aggregate]}});
  const first:SourceCatalogItem={...item,id:"e".repeat(64),parentId:aggregate.id,name:"0",selector:"samples[0]"};
  const second:SourceCatalogItem={...item,id:"f".repeat(64),parentId:aggregate.id,name:"1",selector:"samples[1]"};
  const sourceVariables=vi.fn(async(_query:string,cursor?:string)=>({ok:true as const,data:
   cursor===undefined?{...sourcePage(status),total:2,items:[first],nextCursor:"more"}:
   {...sourcePage(status),total:2,items:[second],nextCursor:null}}));
  const sourceSelection=vi.fn(async()=>({ok:true as const,data:{catalogId:tree(status).catalogId,
   item:{kind:"variable" as const,expression:"samples[0]"}}}));
  const api:MonitorApi={...recordingApi([],status),sourceVariables,sourceSelection};
  const controller=createController(api,action=>{state=reducer(state,action);},()=>state);
  try{
   await controller.selectSource(first);
   expect(sourceSelection).not.toHaveBeenCalled();
   await controller.sourceChildren(aggregate.id);
   expect(state.catalog.source.children[aggregate.id]?.items.map(node=>node.name)).toEqual(["0"]);
   await controller.sourceChildren(aggregate.id,true);
   expect(state.catalog.source.children[aggregate.id]?.items.map(node=>node.name)).toEqual(["0","1"]);
   expect(sourceVariables.mock.calls.map(call=>call[1])).toEqual([undefined,"more"]);
   await controller.selectSource(first);
   expect(sourceSelection).toHaveBeenCalledOnce();
   expect(state.groupDraft.items).toContainEqual({kind:"variable",expression:"samples[0]"});
  }finally{controller.close();}
 });

 it("collects every metadata page before one adoption, independent of queued reducer state",async()=>{
  const status=connected(),calls:string[]=[];
  let committed:MonitorState=reducer(initialState,{type:"initial.loaded",status,probes:[],groups:[]});
  const queued:MonitorAction[]=[];
  const api:MonitorApi={...recordingApi([],status),sourceTree:async(_query,cursor,_parent,catalogId)=>{
   calls.push(`${cursor??"first"}:${catalogId??"none"}`);
   return{ok:true,data:cursor===undefined?{...tree(status,[main]),total:2,nextCursor:"next"}:{...tree(status,[safe]),total:2}};
  }};
  const controller=createController(api,action=>queued.push(action),()=>committed);
  try{
   const request=controller.searchSource("");await request;
   for(const action of queued)committed=reducer(committed,action);
   expect(calls).toEqual(["first:none",`next:${"a".repeat(64)}`]);
   expect(committed.catalog.source.tree?.items.map(node=>node.file)).toEqual([main.file,safe.file]);
  }finally{controller.close();}
 });

 it("keeps two branches independent and retries the failed branch through current admission",async()=>{
  const status=connected();let state:MonitorState=reducer(initialState,{type:"initial.loaded",status,probes:[],groups:[]});
  const contextKey=sourceContextKey(status);
  state=reducer(state,{type:"source.started",query:"",contextKey,generation:state.catalog.source.generation+1n});
  state=reducer(state,{type:"source.tree.loaded",query:"",contextKey,generation:state.catalog.source.generation,
   parentId:null,page:tree(status,[main,safe])});
  let failMain=true;
  const api:MonitorApi={...recordingApi([],status),sourceTree:async(_query,_cursor,parent)=>{
   if(parent===main.id&&failMain)return{ok:false,code:"MONITOR_SOURCE_INDEX_FAILED",message:"failed"};
   return{ok:true,data:{...tree(status),total:1,items:[parent===safe.id?safeScope:mainScope]}};
  }};
  const controller=createController(api,action=>{state=reducer(state,action);},()=>state);
  try{
   await Promise.all([controller.sourceChildren(main.id),controller.sourceChildren(safe.id)]);
   expect(state.catalog.source.branches[safe.id]?.items[0]?.id).toBe(safeScope.id);
   expect(state.failures[`catalog.source-node.${main.id}`]?.code).toBe("MONITOR_SOURCE_INDEX_FAILED");
   failMain=false;
   await controller.retry(`catalog.source-node.${main.id}`,state.failures[`catalog.source-node.${main.id}`]!.requestId);
   expect(state.catalog.source.branches[main.id]?.items[0]?.id).toBe(mainScope.id);
   expect(state.catalog.source.branches[safe.id]?.items[0]?.id).toBe(safeScope.id);
  }finally{controller.close();}
 });

 it("retires tree, branches, pages and late selection after a context change",()=>{
  const status=connected(),before=loaded(status),contextKey=sourceContextKey(status),generation=before.catalog.source.generation;
  const changed={...status,firmware:{...status.firmware!,buildId:"next"}};
  let state=reducer(before,{type:"status.loaded",status:changed});
  expect(state.catalog.source.tree).toBeNull();
  expect(state.catalog.source.branches).toEqual({});
  expect(state.catalog.source.scopePages).toEqual({});
  state=reducer(state,{type:"source.tree.loaded",query:"",contextKey,generation,parentId:null,page:tree(status)});
  state=reducer(state,{type:"source.selection.accepted",contextKey,generation,groupGeneration:before.groupGeneration,
   catalogId:tree(status).catalogId,itemId:item.id,selector:"counter",watch:{kind:"variable",expression:"counter"}});
  expect(state.catalog.source.tree).toBeNull();
  expect(state.groupDraft.items).toEqual([]);
 });

 it("keeps stale firmware leaves readonly and gates an ACK by group generation",()=>{
  const status=connected(),contextKey=sourceContextKey(status);let state=loaded(status);
  state=reducer(state,{type:"source.started",query:"",contextKey,generation:state.catalog.source.generation+1n});
  const stale={...sourcePage(status),identity:{...sourcePage(status).identity,buildId:"new-build"},total:1,items:[item]};
  state=reducer(state,{type:"source.tree.loaded",query:"",contextKey,generation:state.catalog.source.generation,
   parentId:null,page:tree(status)});
  state=reducer(state,{type:"source.tree.loaded",query:"",contextKey,generation:state.catalog.source.generation,
   parentId:main.id,page:{...tree(status),total:1,items:[mainScope]}});
  state=reducer(state,{type:"source.variables.loaded",query:"",contextKey,generation:state.catalog.source.generation,
   cursor:null,parentId:null,scopeId:mainScope.id,page:stale});
  expect(state.catalog.source.scopePages[mainScope.id]?.items[0]?.canAdd).toBe(false);
  const oldGeneration=state.groupGeneration;
  state=reducer(state,{type:"group.navigation.requested",target:{kind:"new"}});
  state=reducer(state,{type:"source.selection.accepted",contextKey,generation:state.catalog.source.generation,
   groupGeneration:oldGeneration,catalogId:tree(status).catalogId,itemId:item.id,selector:"counter",
   watch:{kind:"variable",expression:"counter"}});
  expect(state.groupDraft.items).toEqual([]);
 });

 it("adds only a listed eligible leaf to the current draft",()=>{
  const status=connected(),contextKey=sourceContextKey(status);let state=loaded(status);
  state=reducer(state,{type:"source.selection.accepted",contextKey,generation:state.catalog.source.generation,
   groupGeneration:state.groupGeneration,catalogId:tree(status).catalogId,itemId:item.id,selector:"counter",
   watch:{kind:"variable",expression:"counter"}});
  expect(state.groupDraft.items).toEqual([{kind:"variable",expression:"counter"}]);
  expect(state.catalog.source.lastAddedId).toBe(item.id);
 });
});
