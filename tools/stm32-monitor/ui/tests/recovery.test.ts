import {afterEach,expect,it,vi} from "vitest";
import {createController} from "../src/controller";
import {initialState,reducer} from "../src/state/reducer";
import {statusResult,watchGroup} from "./fixtures";
import type {ApiResult,GroupDraft,GroupPage,HistoryPage,HistoryQuery,MonitorApi,WatchGroup} from "../src/api/contract";
import type {MonitorAction,MonitorState,RequestScope} from "../src/state/model";
import {openLive} from "../src/api/live";

vi.mock("../src/api/live",()=>({openLive:vi.fn(()=>()=>{})}));
afterEach(()=>vi.mocked(openLive).mockClear());
const ok=<T>(data:T)=>({ok:true,data} as const);
const err=(code:string)=>({ok:false,code,message:code} as const);
const page=(groups:readonly WatchGroup[],nextCursor:string|null=null):GroupPage=>({groups,nextCursor,revision:"r1"});
const historyPage=(nextCursor:string|null=null):HistoryPage=>({batches:[],valueCount:0n,nextCursor,serializedBytes:0n});
function deferred<T>(){
  let resolve!:(value:T)=>void;
  const promise=new Promise<T>(r=>{resolve=r;});
  return{promise,resolve};
}
function makeApi(overrides:Partial<MonitorApi>={}):MonitorApi{
  const group=watchGroup();
  return{
    status:vi.fn(async()=>ok(statusResult())),probes:vi.fn(async()=>ok({probes:[]})),
    groups:vi.fn(async()=>ok(page([group]))),
    createGroup:vi.fn(async()=>ok(group)),updateGroup:vi.fn(async()=>ok(group)),
    history:vi.fn(async()=>ok(historyPage())),exportStatus:vi.fn(async()=>ok({exportId:"e1",format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n})),
    createExport:vi.fn(async()=>ok({exportId:"e1",format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n})),
    downloadExport:vi.fn(async()=>err("DOWNLOAD_FAILED")),
    ...overrides,
  } as MonitorApi;
}
function harness(api:MonitorApi){
  let state:MonitorState=initialState;
  const actions:MonitorAction[]=[];
  const dispatch=(action:MonitorAction)=>{state=reducer(state,action);actions.push(action);};
  const controller=createController(api,dispatch,()=>state);
  return{controller,state:()=>state,dispatch,actions};
}
const failureId=(state:MonitorState,scope:RequestScope)=>state.failures[scope]!.requestId;
const draft=(name:string):GroupDraft=>({sourceGroupId:null,expectedRevision:null,name,description:"",intervalMs:250,
  items:[{kind:"variable",expression:"counter"}]});

it("retries the whole initial snapshot after page two fails and opens one live connection",async()=>{
  const group=watchGroup();
  let failed=false;
  const groups=vi.fn(async(cursor?:string)=>{
    if(cursor===undefined)return ok(page([group],"c2"));
    if(!failed){failed=true;return err("GROUPS_DOWN");}
    return ok(page([{...group,groupId:"g2"}]));
  });
  const h=harness(makeApi({groups}));
  await h.controller.loadInitial();
  expect(h.state().status).toBeNull();
  expect(h.state().groups).toHaveLength(0);
  expect(h.state().failures.initial?.recovery).toBe("read-retry");
  expect(openLive).not.toHaveBeenCalled();
  await h.controller.retry("initial",failureId(h.state(),"initial"));
  expect(h.state().groups).toHaveLength(2);
  expect(openLive).toHaveBeenCalledTimes(1);
  await h.controller.loadInitial();
  expect(openLive).toHaveBeenCalledTimes(1);
  h.controller.close();
});

it("prefers fatal access rejection over simultaneous ordinary initial failure",async()=>{
  const h=harness(makeApi({status:vi.fn(async()=>err("STATUS_DOWN")),
    probes:vi.fn(async()=>err("MONITOR_AUTH_REQUIRED"))}));
  await h.controller.loadInitial();
  expect(h.state().blockingError?.code).toBe("MONITOR_AUTH_REQUIRED");
  expect(h.state().failures.initial).toBeUndefined();
  expect(openLive).not.toHaveBeenCalled();
});

it("close and supersession stop stale groups pagination before page two",async()=>{
  const first=deferred<ApiResult<GroupPage>>();
  const groups=vi.fn()
    .mockImplementationOnce(()=>first.promise)
    .mockImplementation(async()=>ok(page([])));
  const h=harness(makeApi({groups}));
  const loading=h.controller.loadInitial();
  h.controller.close();
  first.resolve(ok(page([],"next")));
  await loading;
  expect(groups).toHaveBeenCalledTimes(1);
  expect(openLive).not.toHaveBeenCalled();
  const nextFirst=deferred<ApiResult<GroupPage>>();
  const list=vi.fn().mockImplementationOnce(()=>nextFirst.promise).mockImplementation(async()=>ok(page([])));
  const second=harness(makeApi({groups:list}));
  const stale=second.controller.refreshGroups();
  await second.controller.refreshGroups();
  nextFirst.resolve(ok(page([],"old-next")));
  await stale;
  expect(list).toHaveBeenCalledTimes(2);
});

it("fatal authorization aborts a pending initial group cursor chain",async()=>{
  const first=deferred<ApiResult<GroupPage>>();
  const groups=vi.fn(()=>first.promise);
  const h=harness(makeApi({status:vi.fn(async()=>err("MONITOR_ORIGIN_REJECTED")),groups}));
  const loading=h.controller.loadInitial();
  await Promise.resolve();
  expect(h.state().blockingError?.code).toBe("MONITOR_ORIGIN_REJECTED");
  first.resolve(ok(page([],"must-not-fetch")));
  await loading;
  expect(groups).toHaveBeenCalledTimes(1);
});

it("old success cannot erase newer failure or override access blocking",async()=>{
  const slow=deferred<Awaited<ReturnType<MonitorApi["status"]>>>();
  const api=makeApi({status:vi.fn().mockImplementationOnce(()=>slow.promise)
    .mockImplementationOnce(async()=>err("STATUS_DOWN"))});
  const h=harness(api);
  const old=h.controller.refreshStatus();
  await h.controller.refreshStatus();
  expect(h.state().failures.status?.code).toBe("STATUS_DOWN");
  slow.resolve(ok(statusResult()));
  await old;
  expect(h.state().status).toBeNull();
  expect(h.state().failures.status?.code).toBe("STATUS_DOWN");
  const pendingHistory=deferred<Awaited<ReturnType<MonitorApi["history"]>>>();
  const blocked=harness(makeApi({history:vi.fn(()=>pendingHistory.promise),
    status:vi.fn(async()=>err("MONITOR_PEER_REJECTED"))}));
  const history=blocked.controller.loadHistory({startNs:0n,endNs:1n});
  await blocked.controller.refreshStatus();
  pendingHistory.resolve(ok(historyPage()));
  await history;
  expect(blocked.state().blockingError?.code).toBe("MONITOR_PEER_REJECTED");
  expect(blocked.state().history.page).toBeNull();
});

it("failed complete group refresh preserves its prior list and edited draft",async()=>{
  const existing=watchGroup(),other={...existing,groupId:"other"};
  const groups=vi.fn()
    .mockImplementationOnce(async()=>ok(page([other],"more")))
    .mockImplementationOnce(async()=>err("PAGE_DOWN"))
    .mockImplementationOnce(async()=>ok(page([other],"more")))
    .mockImplementationOnce(async()=>ok(page([existing])));
  const h=harness(makeApi({groups}));
  h.dispatch({type:"initial.loaded",status:statusResult(),probes:[],groups:[existing]});
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"unsaved"}});
  await h.controller.refreshGroups();
  expect(h.state().groups).toEqual([existing]);
  expect(h.state().groupDraft.name).toBe("unsaved");
  await h.controller.retry("groups.list",failureId(h.state(),"groups.list"));
  expect(h.state().groups).toHaveLength(2);
  expect(h.state().groupDraft.name).toBe("unsaved");
});

it("confirmed retry captures original draft and blocks a second group write",async()=>{
  const pending=deferred<Awaited<ReturnType<MonitorApi["createGroup"]>>>();
  const create=vi.fn().mockImplementationOnce(async()=>err("REJECTED"))
    .mockImplementationOnce(()=>pending.promise);
  const h=harness(makeApi({createGroup:create}));
  h.dispatch({type:"group.draft.changed",draft:draft("original")});
  await h.controller.createGroup();
  const id=failureId(h.state(),"groups.create");
  expect(h.state().failures["groups.create"]?.recovery).toBe("write-confirm");
  h.dispatch({type:"group.draft.changed",draft:draft("new draft")});
  const retried=h.controller.retry("groups.create",id);
  await h.controller.retry("groups.create",id);
  await h.controller.createGroup();
  expect(create).toHaveBeenCalledTimes(2);
  expect(create.mock.calls[1]?.[0]?.name).toBe("original");
  pending.resolve(ok(watchGroup()));
  await retried;
  expect(h.state().groupDraft.name).toBe("new draft");
});

it("uncertain group write reconciles once without repeating POST",async()=>{
  const pending=deferred<ApiResult<GroupPage>>();
  const create=vi.fn(async()=>err("MONITOR_TRANSPORT_FAILED"));
  const groups=vi.fn(()=>pending.promise);
  const h=harness(makeApi({createGroup:create,groups}));
  h.dispatch({type:"group.draft.changed",draft:draft("x")});
  await h.controller.createGroup();
  const id=failureId(h.state(),"groups.create");
  expect(h.state().failures["groups.create"]?.recovery).toBe("reconcile");
  const refresh=h.controller.retry("groups.create",id);
  await h.controller.retry("groups.create",id);
  expect(groups).toHaveBeenCalledTimes(1);
  expect(create).toHaveBeenCalledTimes(1);
  expect(h.state().reconciling["groups.create"]).toBe(id);
  pending.resolve(ok(page([])));
  await refresh;
  expect(h.state().reconciling["groups.create"]).toBeUndefined();
  expect(h.state().failures["groups.create"]?.requestId).toBe(id);
});

it("accepted group create keeps its identity and family lock through failed follow-up GET",async()=>{
  const created={...watchGroup(),groupId:"created",revision:7n};
  const pending=deferred<ApiResult<GroupPage>>();
  const create=vi.fn(async()=>ok(created));
  const groups=vi.fn(()=>pending.promise);
  const h=harness(makeApi({createGroup:create,groups}));
  h.dispatch({type:"group.draft.changed",draft:draft("saved")});
  const saving=h.controller.createGroup();
  await Promise.resolve();
  expect(h.state().groupDraft.sourceGroupId).toBe("created");
  expect(h.state().groupDraft.expectedRevision).toBe(7n);
  await h.controller.createGroup();
  expect(create).toHaveBeenCalledTimes(1);
  pending.resolve(err("GROUPS_DOWN"));
  await saving;
  expect(h.state().failures["groups.list"]?.code).toBe("GROUPS_DOWN");
  await h.controller.createGroup();
  expect(create).toHaveBeenCalledTimes(1);
});

it("history failed forward and backward retries update the accepted stack only on success",async()=>{
  const responses=[err("FORWARD_DOWN"),ok(historyPage(null)),err("BACK_DOWN"),ok(historyPage("c2"))];
  const calls:HistoryQuery[]=[];
  const api=makeApi({history:vi.fn(async(query)=>{calls.push({...query});return responses.shift()!;})});
  const h=harness(api);
  h.dispatch({type:"history.loaded",query:{startNs:0n,endNs:2n},page:historyPage("c2")});
  await h.controller.nextHistory("c2");
  expect(h.state().history.cursorStack).toEqual([]);
  expect(h.state().history.query?.cursor).toBeUndefined();
  await h.controller.retry("history",failureId(h.state(),"history"));
  expect(h.state().history.cursorStack).toEqual([undefined]);
  expect(h.state().history.query?.cursor).toBe("c2");
  await h.controller.nextHistory(undefined);
  expect(h.state().history.cursorStack).toEqual([undefined]);
  await h.controller.retry("history",failureId(h.state(),"history"));
  expect(h.state().history.cursorStack).toEqual([]);
  expect(h.state().history.query?.cursor).toBeUndefined();
  expect(calls.map(query=>query.cursor)).toEqual(["c2","c2",undefined,undefined]);
});

it("export range stays bound to its ID; stale status cannot replace a newer create",async()=>{
  const old=deferred<Awaited<ReturnType<MonitorApi["exportStatus"]>>>();
  const artifact=(id:string)=>({exportId:id,format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n});
  const create=vi.fn().mockImplementationOnce(async()=>ok(artifact("e1")))
    .mockImplementationOnce(async()=>ok(artifact("e2")));
  const h=harness(makeApi({createExport:create,exportStatus:vi.fn(()=>old.promise)}));
  await h.controller.createExport(1n,2n,"csv");
  const oldStatus=h.controller.refreshExport("e1");
  await h.controller.createExport(3n,4n,"csv");
  old.resolve(ok(artifact("e1")));
  await oldStatus;
  expect(h.state().exports.artifact?.exportId).toBe("e2");
  expect(h.state().exports.submitted).toEqual({exportId:"e2",startNs:3n,endNs:4n,format:"csv"});
});

it("export status and download failures settle and retry their captured task ID",async()=>{
  const artifact={exportId:"e1",format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n};
  const status=vi.fn().mockImplementationOnce(async()=>err("STATUS_DOWN"))
    .mockImplementationOnce(async()=>ok({...artifact,bytes:2n}));
  const download=vi.fn(async(exportId:string)=>{void exportId;return err("DOWNLOAD_DOWN");});
  const h=harness(makeApi({createExport:vi.fn(async()=>ok(artifact)),exportStatus:status,downloadExport:download}));
  await h.controller.createExport(10n,20n,"csv");
  await h.controller.refreshExport("e1");
  expect(h.state().pending["export.status"]).toBeUndefined();
  expect(h.state().exports.artifact?.bytes).toBe(1n);
  await h.controller.retry("export.status",failureId(h.state(),"export.status"));
  expect(h.state().exports.artifact?.bytes).toBe(2n);
  expect(h.state().exports.submitted?.startNs).toBe(10n);
  await h.controller.downloadExport("e1");
  const id=failureId(h.state(),"export.download");
  expect(h.state().pending["export.download"]).toBeUndefined();
  await h.controller.retry("export.download",id);
  expect(download).toHaveBeenCalledTimes(2);
  expect(download.mock.calls.every(call=>call[0]==="e1")).toBe(true);
});
