// @vitest-environment node
import {expect,it,vi} from "vitest";
import {createController} from "../src/controller";
import {initialState,reducer} from "../src/state/reducer";
import {emptyDraft,type MonitorAction,type MonitorState} from "../src/state/model";
import {statusResult,watchGroup} from "./fixtures";
import type {ApiResult,GroupPage,MonitorApi,WatchGroup} from "../src/api/contract";

const ok=<T>(data:T)=>({ok:true,data} as const);
const err=(code:string)=>({ok:false,code,message:code} as const);
const page=(groups:readonly WatchGroup[]):GroupPage=>({groups,nextCursor:null,revision:"r1"});
function deferred<T>(){
  let resolve!:(value:T)=>void;
  const promise=new Promise<T>(r=>{resolve=r;});
  return{promise,resolve};
}
function harness(overrides:Partial<MonitorApi>={},groups:readonly WatchGroup[]=[watchGroup()]){
  const api={groups:vi.fn(async()=>ok(page(groups))),createGroup:vi.fn(async()=>ok(watchGroup())),
    updateGroup:vi.fn(async()=>ok(watchGroup())),deleteGroup:vi.fn(async(groupId:string)=>ok({groupId,deleted:true as const})),
    importGroups:vi.fn(async()=>ok([])),...overrides} as MonitorApi;
  let state:MonitorState=reducer(initialState,{type:"initial.loaded",status:statusResult(),probes:[],groups});
  const actions:MonitorAction[]=[];
  const dispatch=(action:MonitorAction)=>{state=reducer(state,action);actions.push(action);};
  return{api,controller:createController(api,dispatch,()=>state),state:()=>state,dispatch,actions};
}
const group=(id:string,name:string,revision=1n):WatchGroup=>({...watchGroup(),groupId:id,name,revision});

it("keeps a dirty draft on same-group click and requires explicit navigation confirmation",()=>{
  const first=group("first","First"),second=group("second","Second");
  const h=harness({},[first,second]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Unsent"}});
  const before=h.state().groupDraft;
  h.dispatch({type:"group.navigation.requested",target:{kind:"group",groupId:"first"}});
  expect(h.state().groupDraft).toEqual(before);
  expect(h.state().groupNavigation).toBeNull();
  h.dispatch({type:"group.navigation.requested",target:{kind:"group",groupId:"second"}});
  expect(h.state().groupDraft).toEqual(before);
  expect(h.state().selectedGroupId).toBe("first");
  expect(h.state().groupNavigation).toEqual({kind:"group",groupId:"second"});
  h.dispatch({type:"group.navigation.cancelled"});
  expect(h.state().groupDraft).toEqual(before);
  h.dispatch({type:"group.navigation.requested",target:{kind:"new"}});
  h.dispatch({type:"group.navigation.confirmed"});
  expect(h.state().groupDraft).toEqual(emptyDraft);
  expect(h.state().selectedGroupId).toBeNull();
  expect(h.state().groupGeneration).toBeGreaterThan(0n);
});

it("retains a dirty orphan after refresh but blocks UPDATE until an explicit save-as-new",async()=>{
  const first=group("first","First"),h=harness({groups:vi.fn(async()=>ok(page([])))},[first]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Rescue"}});
  await h.controller.refreshGroups();
  expect(h.state().groupDraft.sourceGroupId).toBe("first");
  expect(h.state().groupDraft.name).toBe("Rescue");
  expect(h.state().selectedGroupId).toBeNull();
  await h.controller.saveGroup(h.state().groupDraft);
  expect(h.api.updateGroup).not.toHaveBeenCalled();
  h.dispatch({type:"group.save-as-new"});
  expect(h.state().groupDraft).toMatchObject({sourceGroupId:null,expectedRevision:null,name:"Rescue"});
  expect(h.state().selectedGroupId).toBeNull();
  expect(h.state().groupNameReviewRequired).toBe(true);
  await h.controller.saveGroup(h.state().groupDraft);
  expect(h.api.createGroup).not.toHaveBeenCalled();
  h.dispatch({type:"group.name.reviewed"});
  await h.controller.saveGroup(h.state().groupDraft);
  expect(h.api.createGroup).toHaveBeenCalledTimes(1);
});

it("keeps the old revision until a dirty draft explicitly reloads the latest group",async()=>{
  const first=group("first","First"),latest={...first,name:"Server",revision:2n};
  const h=harness({groups:vi.fn(async()=>ok(page([latest])))},[first]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Local"}});
  await h.controller.refreshGroups();
  expect(h.state().groupDraft).toMatchObject({name:"Local",expectedRevision:1n});
  await h.controller.saveGroup(h.state().groupDraft);
  expect(h.api.updateGroup).not.toHaveBeenCalled();
  h.dispatch({type:"group.navigation.requested",target:{kind:"reload",groupId:"first"}});
  expect(h.state().groupNavigation).toEqual({kind:"reload",groupId:"first"});
  h.dispatch({type:"group.navigation.confirmed"});
  expect(h.state().groupDraft).toMatchObject({name:"Server",expectedRevision:2n});
});

it("does not discard a draft if its confirmed navigation target vanished",()=>{
  const first=group("first","First"),second=group("second","Second"),h=harness({},[first,second]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Local"}});
  h.dispatch({type:"group.navigation.requested",target:{kind:"group",groupId:"second"}});
  h.dispatch({type:"groups.loaded",groups:[first]});
  h.dispatch({type:"group.navigation.confirmed"});
  expect(h.state().groupDraft.name).toBe("Local");
  expect(h.state().selectedGroupId).toBe("first");
  expect(h.state().groupNavigationMissing).toBe(true);
});

it("accepts save before a failing follow-up GET and retries only the GET",async()=>{
  const existing=group("first","First"),saved=group("first","Updated",2n);
  const update=vi.fn(async()=>ok(saved));
  const groups=vi.fn().mockResolvedValueOnce(err("GROUPS_DOWN")).mockResolvedValueOnce(ok(page([saved])));
  const h=harness({updateGroup:update,groups},[existing]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Updated"}});
  await h.controller.saveGroup(h.state().groupDraft);
  expect(h.state().groupDraft).toMatchObject({sourceGroupId:"first",expectedRevision:2n,name:"Updated"});
  expect(h.state().groups[0]).toEqual(saved);
  expect(h.state().failures["groups.list"]?.code).toBe("GROUPS_DOWN");
  await h.controller.retry("groups.list",h.state().failures["groups.list"]!.requestId);
  expect(update).toHaveBeenCalledTimes(1);
  expect(groups).toHaveBeenCalledTimes(2);
});

it("conflict recovery reads only, then same-revision rename is a fresh submit",async()=>{
  const existing=group("first","First");
  const update=vi.fn().mockResolvedValueOnce(err("MONITOR_GROUP_CONFLICT"))
    .mockResolvedValueOnce(ok({...existing,name:"Different",revision:2n}));
  const groups=vi.fn(async()=>ok(page([existing])));
  const h=harness({updateGroup:update,groups},[existing]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Collision"}});
  await h.controller.saveGroup(h.state().groupDraft);
  const id=h.state().failures["groups.update"]!.requestId;
  expect(h.state().failures["groups.update"]?.recovery).toBe("groups-refresh");
  await h.controller.retry("groups.update",id);
  expect(groups).toHaveBeenCalledTimes(1);
  expect(update).toHaveBeenCalledTimes(1);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Different"}});
  await h.controller.saveGroup(h.state().groupDraft);
  expect(update).toHaveBeenCalledTimes(2);
});

it("blocks group writes until a post-conflict list GET succeeds, even after dismissal or a failed GET",async()=>{
  const existing=group("first","First");
  const update=vi.fn().mockResolvedValueOnce(err("MONITOR_GROUP_CONFLICT"))
    .mockResolvedValueOnce(ok({...existing,name:"Fresh",revision:2n}));
  const groups=vi.fn().mockResolvedValueOnce(err("GROUPS_DOWN")).mockResolvedValueOnce(ok(page([existing])));
  const h=harness({updateGroup:update,groups},[existing]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Collision"}});
  await h.controller.saveGroup(h.state().groupDraft);
  expect(h.state().failures["groups.update"]?.recovery).toBe("groups-refresh");
  await h.controller.saveGroup(h.state().groupDraft);
  expect(update).toHaveBeenCalledTimes(1);
  const failedId=h.state().failures["groups.update"]!.requestId;
  h.controller.dismiss("groups.update",failedId);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Fresh"}});
  await h.controller.saveGroup(h.state().groupDraft);
  expect(update).toHaveBeenCalledTimes(1);
  await h.controller.refreshGroups();
  expect(h.state().failures["groups.list"]?.code).toBe("GROUPS_DOWN");
  await h.controller.saveGroup(h.state().groupDraft);
  expect(update).toHaveBeenCalledTimes(1);
  await h.controller.retry("groups.list",h.state().failures["groups.list"]!.requestId);
  await h.controller.saveGroup(h.state().groupDraft);
  expect(update).toHaveBeenCalledTimes(2);
  expect(update).toHaveBeenLastCalledWith("first",expect.objectContaining({expectedRevision:1n,name:"Fresh"}));
});

it("fences a queued conflict and waits for the successful GET snapshot to reach reducer state",async()=>{
  const existing=group("first","First");
  let state=reducer(initialState,{type:"initial.loaded",status:statusResult(),probes:[],groups:[existing]});
  state=reducer(state,{type:"group.draft.changed",draft:{...state.groupDraft,name:"Fresh"}});
  const queued:MonitorAction[]=[];
  const dispatch=(action:MonitorAction)=>{queued.push(action);};
  const flush=()=>{for(const action of queued.splice(0))state=reducer(state,action);};
  const update=vi.fn().mockResolvedValueOnce(err("MONITOR_GROUP_CONFLICT"))
    .mockResolvedValueOnce(ok({...existing,name:"Fresh",revision:2n}));
  const groups=vi.fn(async()=>ok(page([existing])));
  const controller=createController({updateGroup:update,groups} as unknown as MonitorApi,dispatch,()=>state);
  await controller.saveGroup(state.groupDraft);
  await controller.saveGroup(state.groupDraft);
  expect(update).toHaveBeenCalledTimes(1);
  flush();
  expect(state.groupsNeedRefresh).toBe(true);
  await controller.refreshGroups();
  await controller.saveGroup(state.groupDraft);
  expect(update).toHaveBeenCalledTimes(1);
  flush();
  expect(state.groupsNeedRefresh).toBe(false);
  await controller.saveGroup(state.groupDraft);
  expect(update).toHaveBeenCalledTimes(2);
});

it("applies the conflict refresh gate to create, delete, and import without locking draft navigation",async()=>{
  const existing=group("first","First");
  const create=vi.fn(async()=>ok(group("new","New")));
  const remove=vi.fn(async()=>ok({groupId:"first",deleted:true as const}));
  const imported=vi.fn(async()=>ok([]));
  const h=harness({updateGroup:vi.fn(async()=>err("MONITOR_GROUP_CONFLICT")),createGroup:create,
    deleteGroup:remove,importGroups:imported},[existing]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Collision"}});
  await h.controller.saveGroup(h.state().groupDraft);
  await h.controller.deleteGroup("first",1n,h.state().groupGeneration);
  await h.controller.importGroups({schemaVersion:1,groups:[]});
  h.dispatch({type:"group.save-as-new"});
  expect(h.state().groupDraft.sourceGroupId).toBeNull();
  h.dispatch({type:"group.name.reviewed"});
  await h.controller.createGroup();
  expect(remove).not.toHaveBeenCalled();
  expect(imported).not.toHaveBeenCalled();
  expect(create).not.toHaveBeenCalled();
  expect(h.state().groupsNeedRefresh).toBe(true);
});

it("import name conflict refreshes without replay and preserves the editing draft",async()=>{
  const imported=vi.fn(async()=>err("MONITOR_IMPORT_CONFLICT"));
  const groups=vi.fn(async()=>ok(page([group("first","First")])));
  const h=harness({importGroups:imported,groups},[group("first","First")]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Unsaved"}});
  await h.controller.importGroups({schemaVersion:1,groups:[{name:"Collision",description:"",intervalMs:250,items:[]}]});
  const id=h.state().failures["groups.import"]!.requestId;
  expect(h.state().failures["groups.import"]?.recovery).toBe("groups-refresh");
  await h.controller.retry("groups.import",id);
  expect(imported).toHaveBeenCalledTimes(1);
  expect(groups).toHaveBeenCalledTimes(1);
  expect(h.state().groupDraft.name).toBe("Unsaved");
});

it("locks reducer editing and navigation during a group list or write",()=>{
  const first=group("first","First"),h=harness({},[first]);
  const before=h.state().groupDraft;
  h.dispatch({type:"request.started",scope:"groups.list",requestId:10n});
  h.dispatch({type:"group.navigation.requested",target:{kind:"new"}});
  h.dispatch({type:"group.draft.changed",draft:{...before,name:"ignored"}});
  h.dispatch({type:"group.watch.added",watch:{kind:"variable",expression:"extra"}});
  expect(h.state().groupDraft).toEqual(before);
  expect(h.state().groupNavigation).toBeNull();
  h.dispatch({type:"request.cleared",scope:"groups.list",requestId:10n});
  h.dispatch({type:"group.write.started"});
  h.dispatch({type:"group.watch.removed",key:"variable:counter"});
  expect(h.state().groupDraft).toEqual(before);
});

it("holds an existing navigation decision through a group write lock",()=>{
  const first=group("first","First"),second=group("second","Second"),h=harness({},[first,second]);
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Unsaved"}});
  h.dispatch({type:"group.navigation.requested",target:{kind:"group",groupId:"second"}});
  h.dispatch({type:"group.write.started"});
  h.dispatch({type:"group.navigation.cancelled"});
  h.dispatch({type:"group.navigation.confirmed"});
  expect(h.state().groupNavigation).toEqual({kind:"group",groupId:"second"});
  expect(h.state().groupDraft.name).toBe("Unsaved");
});

it("retires an older list before write, locks concurrent actions, and applies delete/import acknowledgements",async()=>{
  const existing=group("first","First"),late=deferred<ApiResult<GroupPage>>();
  const deleteAck=deferred<Awaited<ReturnType<MonitorApi["deleteGroup"]>>>();
  const groups=vi.fn().mockImplementationOnce(()=>late.promise).mockResolvedValue(ok(page([])));
  const remove=vi.fn(()=>deleteAck.promise);
  const h=harness({groups,deleteGroup:remove,createGroup:vi.fn(async()=>ok(group("new","New")))},[existing]);
  const old=h.controller.refreshGroups();
  const deleting=h.controller.deleteGroup("first");
  await h.controller.createGroup();
  expect(h.api.createGroup).not.toHaveBeenCalled();
  deleteAck.resolve(ok({groupId:"first",deleted:true}));
  await deleting;
  expect(h.state().selectedGroupId).toBeNull();
  expect(h.state().groupDraft.sourceGroupId).toBeNull();
  late.resolve(ok(page([existing])));
  await old;
  expect(h.state().groups.some(item=>item.groupId==="first")).toBe(false);

  const imported=group("imported","Imported");
  const followup=deferred<ApiResult<GroupPage>>();
  const importing=harness({importGroups:vi.fn(async()=>ok([imported])),groups:vi.fn(()=>followup.promise)},[existing]);
  const call=importing.controller.importGroups({schemaVersion:1,groups:[]});
  await Promise.resolve();
  expect(importing.state().groups.some(item=>item.groupId==="imported")).toBe(true);
  expect(importing.state().groupDraft.sourceGroupId).toBe("first");
  followup.resolve(err("GROUPS_DOWN"));
  await call;
  expect(importing.state().groups.some(item=>item.groupId==="imported")).toBe(true);
});

it("removes a deleted target before a failing list and never updates that ID again",async()=>{
  const first=group("first","First"),remove=vi.fn(async()=>ok({groupId:"first",deleted:true as const}));
  const update=vi.fn(async()=>ok(first));
  const h=harness({deleteGroup:remove,updateGroup:update,groups:vi.fn(async()=>err("GROUPS_DOWN"))},[first]);
  const staleDraft=h.state().groupDraft;
  await h.controller.deleteGroup("first",1n,h.state().groupGeneration);
  expect(h.state().groups).toEqual([]);
  expect(h.state().selectedGroupId).toBeNull();
  expect(h.state().groupDraft.sourceGroupId).toBeNull();
  expect(h.state().failures["groups.list"]?.code).toBe("GROUPS_DOWN");
  await h.controller.saveGroup(staleDraft);
  expect(update).not.toHaveBeenCalled();
});

it("refuses an old delete confirmation after revision or editor generation changes",async()=>{
  const first=group("first","First"),remove=vi.fn(async()=>ok({groupId:"first",deleted:true as const}));
  const h=harness({deleteGroup:remove},[first]);
  const generation=h.state().groupGeneration;
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"Local"}});
  h.dispatch({type:"groups.loaded",groups:[{...first,revision:2n}]});
  expect(h.state().groupGeneration).toBe(generation);
  await h.controller.deleteGroup("first",1n,generation);
  expect(remove).not.toHaveBeenCalled();
  const next=harness({deleteGroup:remove},[first]);
  const oldGeneration=next.state().groupGeneration;
  next.dispatch({type:"group.navigation.requested",target:{kind:"new"}});
  await next.controller.deleteGroup("first",1n,oldGeneration);
  expect(remove).not.toHaveBeenCalled();
});
