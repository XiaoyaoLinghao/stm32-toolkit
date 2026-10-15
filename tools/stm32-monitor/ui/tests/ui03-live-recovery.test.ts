import {beforeEach,expect,it,vi} from "vitest";
import {createController} from "../src/controller";
import {openLive} from "../src/api/live";
import {initialState,reducer} from "../src/state/reducer";
import {statusResult,watchGroup} from "./fixtures";
import type {ApiResult,LiveHandlers,MonitorApi,MonitorStatus} from "../src/api/contract";
import type {MonitorAction,MonitorState} from "../src/state/model";

vi.mock("../src/api/live",()=>({openLive:vi.fn()}));
const ok=<T>(data:T):ApiResult<T>=>({ok:true,data});
const failed=(code:string):ApiResult<MonitorStatus>=>({ok:false,code,message:code});
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>{resolve=done;});return{promise,resolve};}
function harness(status=vi.fn(async()=>ok(statusResult()))){
  const sockets:{cursor:bigint|null;handlers:LiveHandlers;close:ReturnType<typeof vi.fn>}[]=[];
  vi.mocked(openLive).mockImplementation((_origin,cursor,handlers)=>{
    const socket={cursor,handlers,close:vi.fn()};sockets.push(socket);return socket.close;
  });
  const api={status,probes:vi.fn(async()=>ok({probes:[]})),groups:vi.fn(async()=>ok({groups:[watchGroup()],nextCursor:null,revision:"0"})),
    connect:vi.fn(),reconnect:vi.fn(),release:vi.fn(),start:vi.fn(),pause:vi.fn(),resume:vi.fn(),stop:vi.fn()} as unknown as MonitorApi;
  let state:MonitorState=initialState;
  const actions:MonitorAction[]=[];
  const queued:MonitorAction[]=[];
  let queueActions=false;
  const dispatch=(action:MonitorAction)=>{actions.push(action);if(queueActions)queued.push(action);else state=reducer(state,action);};
  const controller=createController(api,dispatch,()=>state);
  return{controller,api,sockets,actions,state:()=>state,dispatch,
    queueDispatch:()=>{queueActions=true;},
    flushDispatch:()=>{queueActions=false;for(const action of queued.splice(0))state=reducer(state,action);}};
}
beforeEach(()=>vi.mocked(openLive).mockReset());

it("waits for actual open and keeps retained data stale through hello and heartbeat",async()=>{
  const h=harness();await h.controller.loadInitial();
  expect(h.state().transport.phase).toBe("connecting");
  expect(h.state().transport.open).toBe(false);
  h.sockets[0]!.handlers.onOpen();
  expect(h.state().transport.phase).toBe("open");
  expect(h.state().transport.stale).toBe(true);
  for(const [eventId,type] of [[1n,"hello"],[2n,"heartbeat"]] as const){
    const event=type==="hello"
      ?{eventId,type,data:{protocol:"stm32-toolkit-monitor/1" as const,toolkitVersion:"1",monitorVersion:"1",stateRevision:1n}}
      :{eventId,type,data:{stateRevision:1n,capturedAtUtc:"now"}};
    h.sockets[0]!.handlers.onEnvelope({event,subscriberDropped:0n});
    expect(h.state().transport.stale).toBe(true);
  }
  h.controller.close();
});

it("retries the complete identity-only recovery with the same cursor and no write",async()=>{
  const status=vi.fn().mockResolvedValueOnce(ok(statusResult())).mockResolvedValueOnce(failed("STATUS_DOWN"))
    .mockResolvedValueOnce(ok(statusResult()));
  const h=harness(status);await h.controller.loadInitial();
  h.sockets[0]!.handlers.onOpen();
  h.sockets[0]!.handlers.onEnvelope({event:{eventId:41n,type:"heartbeat",data:{stateRevision:1n,capturedAtUtc:"now"}},subscriberDropped:0n});
  h.sockets[0]!.handlers.onClosed();
  const prior=h.state().status;
  await h.controller.reconnectLive();
  expect(h.state().failures["live.reconnect"]?.code).toBe("STATUS_DOWN");
  expect(h.sockets).toHaveLength(1);
  await h.controller.retry("live.reconnect",h.state().failures["live.reconnect"]!.requestId);
  expect(h.sockets).toHaveLength(2);
  expect(h.sockets[1]!.cursor).toBe(41n);
  expect(h.state().status).toBe(prior);
  expect(h.actions.filter(a=>a.type==="status.loaded")).toHaveLength(0);
  h.sockets[1]!.handlers.onOpen();
  expect(h.state().pending["live.reconnect"]).toBeUndefined();
  for(const name of ["connect","reconnect","release","start","pause","resume","stop"] as const)
    expect(h.api[name]).not.toHaveBeenCalled();
  h.controller.close();
});

it("cancels a pending GET and ignores its late result; session change blocks old workbench",async()=>{
  const slow=deferred<ApiResult<MonitorStatus>>();
  const changed={...statusResult(),sessionId:"other-session"};
  const status=vi.fn().mockResolvedValueOnce(ok(statusResult())).mockImplementationOnce(()=>slow.promise)
    .mockResolvedValueOnce(ok(changed));
  const h=harness(status);await h.controller.loadInitial();h.sockets[0]!.handlers.onClosed();
  const pending=h.controller.reconnectLive();
  expect(h.state().transport.phase).toBe("checking");
  h.controller.cancelLiveReconnect();
  slow.resolve(ok(statusResult()));await pending;
  expect(h.sockets).toHaveLength(1);
  expect(h.state().pending["live.reconnect"]).toBeUndefined();
  await h.controller.reconnectLive();
  expect(h.state().blockingError?.code).toBe("MONITOR_SESSION_EXPIRED");
  expect(h.sockets).toHaveLength(1);
  h.controller.close();
});

it("never publishes a preflight A snapshot ahead of ordered B then A replay",async()=>{
  const a=statusResult(),b={...a,sampling:{...a.sampling,bindingEpoch:1n,runId:"B"}};
  const h=harness(vi.fn(async()=>ok(a)));
  await h.controller.loadInitial();h.sockets[0]!.handlers.onClosed();
  await h.controller.reconnectLive();
  expect(h.state().status?.sampling.runId).toBeNull();
  h.sockets[1]!.handlers.onOpen();
  h.sockets[1]!.handlers.onEnvelope({event:{eventId:1n,type:"state",data:{stateRevision:1n,gap:false,status:b}},subscriberDropped:0n});
  expect(h.state().status?.sampling.runId).toBe("B");
  h.sockets[1]!.handlers.onEnvelope({event:{eventId:2n,type:"state",data:{stateRevision:2n,gap:false,status:a}},subscriberDropped:0n});
  expect(h.state().status?.sampling.runId).toBeNull();
  h.controller.close();
});

it("keeps a newer live revision when an older status GET completes",async()=>{
  const slow=deferred<ApiResult<MonitorStatus>>();
  const h=harness(vi.fn().mockResolvedValueOnce(ok(statusResult())).mockImplementationOnce(()=>slow.promise));
  await h.controller.loadInitial();h.sockets[0]!.handlers.onOpen();
  h.sockets[0]!.handlers.onEnvelope({event:{eventId:1n,type:"state",data:{stateRevision:1n,gap:true,status:statusResult()}},subscriberDropped:0n});
  const reading=h.controller.refreshStatus();
  const newer={...statusResult(),sampling:{...statusResult().sampling,bindingEpoch:2n}};
  h.sockets[0]!.handlers.onEnvelope({event:{eventId:2n,type:"state",data:{stateRevision:2n,gap:false,status:newer}},subscriberDropped:0n});
  slow.resolve(ok(statusResult()));await reading;
  expect(h.state().transport.needsStatusRefresh).toBe(true);
  expect(h.state().status?.sampling.bindingEpoch).toBe(2n);
  expect(h.state().pending.status).toBeUndefined();
  h.controller.close();
});

it("keeps a new gap seen while a status GET is in flight",async()=>{
  const slow=deferred<ApiResult<MonitorStatus>>();
  const h=harness(vi.fn().mockResolvedValueOnce(ok(statusResult())).mockImplementationOnce(()=>slow.promise));
  await h.controller.loadInitial();h.sockets[0]!.handlers.onOpen();
  h.sockets[0]!.handlers.onEnvelope({event:{eventId:1n,type:"state",data:{stateRevision:1n,gap:true,status:statusResult()}},subscriberDropped:0n});
  const reading=h.controller.refreshStatus();
  h.sockets[0]!.handlers.onEnvelope({event:{eventId:2n,type:"state",data:{stateRevision:1n,gap:true,status:statusResult()}},subscriberDropped:0n});
  slow.resolve(ok(statusResult()));await reading;
  expect(h.state().transport.gapRevision).toBe(2n);
  expect(h.state().transport.needsStatusRefresh).toBe(true);
  h.controller.close();
});

it.each(["gap","state revision"] as const)("starts a status retry against the current %s generation",async kind=>{
  const refreshed={...statusResult(),sampling:{...statusResult().sampling,bindingEpoch:9n}};
  const status=vi.fn().mockResolvedValueOnce(ok(statusResult())).mockResolvedValueOnce(failed("STATUS_DOWN"))
    .mockResolvedValueOnce(ok(refreshed));
  const h=harness(status);await h.controller.loadInitial();h.sockets[0]!.handlers.onOpen();
  await h.controller.refreshStatus();
  const failureId=h.state().failures.status!.requestId;
  h.sockets[0]!.handlers.onEnvelope({event:{eventId:1n,type:"state",
    data:{stateRevision:1n,gap:kind==="gap",status:statusResult()}},subscriberDropped:0n});
  await h.controller.retry("status",failureId);
  expect(status).toHaveBeenCalledTimes(3);
  expect(h.state().status?.sampling.bindingEpoch).toBe(9n);
  expect(h.state().transport.needsStatusRefresh).toBe(false);
  expect(h.state().failures.status).toBeUndefined();
  h.controller.close();
});

it("guards an old status retry through queued checking and connecting, then permits it after cancel",async()=>{
  const preflight=deferred<ApiResult<MonitorStatus>>();
  const status=vi.fn().mockResolvedValueOnce(ok(statusResult())).mockResolvedValueOnce(failed("STATUS_DOWN"))
    .mockImplementationOnce(()=>preflight.promise).mockResolvedValueOnce(ok(statusResult()));
  const h=harness(status);await h.controller.loadInitial();h.sockets[0]!.handlers.onOpen();
  await h.controller.refreshStatus();
  const failureId=h.state().failures.status!.requestId;
  h.sockets[0]!.handlers.onClosed();
  h.queueDispatch();
  const recovery=h.controller.reconnectLive();
  expect(h.state().transport.phase).toBe("disconnected");
  await h.controller.retry("status",failureId);
  expect(status).toHaveBeenCalledTimes(3);
  preflight.resolve(ok(statusResult()));await recovery;
  expect(h.sockets).toHaveLength(2);
  expect(h.state().transport.phase).toBe("disconnected");
  await h.controller.retry("status",failureId);
  expect(status).toHaveBeenCalledTimes(3);
  h.controller.cancelLiveReconnect();h.flushDispatch();
  await h.controller.retry("status",failureId);
  expect(status).toHaveBeenCalledTimes(4);
  expect(h.state().failures.status).toBeUndefined();
  h.controller.close();
});

it("retries only the fresh status GET after a successful sampling write",async()=>{
  const refreshed={...statusResult(),sampling:{...statusResult().sampling,bindingEpoch:9n}};
  const status=vi.fn().mockResolvedValueOnce(ok(statusResult())).mockResolvedValueOnce(failed("STATUS_DOWN"))
    .mockResolvedValueOnce(ok(refreshed));
  const h=harness(status);await h.controller.loadInitial();h.sockets[0]!.handlers.onOpen();
  vi.mocked(h.api.start).mockResolvedValue(ok({groupId:"group",groupRevision:1n,runId:"run",intervalMs:250}));
  await h.controller.startSampling("group",1n);
  expect(h.api.start).toHaveBeenCalledTimes(1);
  const failureId=h.state().failures.status!.requestId;
  h.sockets[0]!.handlers.onEnvelope({event:{eventId:1n,type:"state",
    data:{stateRevision:1n,gap:true,status:statusResult()}},subscriberDropped:0n});
  await h.controller.retry("status",failureId);
  expect(h.api.start).toHaveBeenCalledTimes(1);
  expect(status).toHaveBeenCalledTimes(3);
  expect(h.state().status?.sampling.bindingEpoch).toBe(9n);
  expect(h.state().transport.needsStatusRefresh).toBe(false);
  h.controller.close();
});

it("recovers after the initial socket constructor throws and settles error plus close once",async()=>{
  vi.mocked(openLive).mockImplementationOnce(()=>{throw new Error("socket unavailable");});
  const h=harness();
  await h.controller.loadInitial();
  expect(h.state().status).not.toBeNull();
  expect(h.state().transport.phase).toBe("disconnected");
  expect(h.state().pending.initial).toBeUndefined();
  await h.controller.reconnectLive();
  expect(h.sockets).toHaveLength(1);
  const callbacks=h.sockets[0]!.handlers;
  callbacks.onFailed();callbacks.onClosed();
  expect(h.state().transport.phase).toBe("disconnected");
  expect(h.actions.filter(a=>a.type==="request.failed"&&a.scope==="live.reconnect")).toHaveLength(1);
  expect(h.sockets[0]!.close).toHaveBeenCalledTimes(1);
  await h.controller.retry("live.reconnect",h.state().failures["live.reconnect"]!.requestId);
  expect(h.sockets).toHaveLength(2);
  expect(h.api.status).toHaveBeenCalledTimes(3);
  h.controller.close();
});

it("cancels a connecting socket, ignores its late callbacks, and permits one replacement",async()=>{
  const h=harness();await h.controller.loadInitial();
  h.controller.cancelLiveReconnect();
  expect(h.sockets[0]!.close).toHaveBeenCalledTimes(1);
  h.sockets[0]!.handlers.onOpen();h.sockets[0]!.handlers.onClosed();
  expect(h.state().transport.phase).toBe("disconnected");
  const first=h.controller.reconnectLive(),second=h.controller.reconnectLive();
  await Promise.all([first,second]);
  expect(h.sockets).toHaveLength(2);
  expect(h.state().transport.phase).toBe("connecting");
  h.controller.cancelLiveReconnect();
  h.sockets[1]!.handlers.onOpen();
  expect(h.state().transport.phase).toBe("disconnected");
  h.controller.close();
});

it("ignores an ordinary GET failure after cancellation",async()=>{
  const slow=deferred<ApiResult<MonitorStatus>>();
  const h=harness(vi.fn().mockResolvedValueOnce(ok(statusResult())).mockImplementationOnce(()=>slow.promise));
  await h.controller.loadInitial();h.sockets[0]!.handlers.onClosed();
  const recovery=h.controller.reconnectLive();h.controller.cancelLiveReconnect();
  slow.resolve(failed("STATUS_DOWN"));await recovery;
  expect(h.state().failures["live.reconnect"]).toBeUndefined();
  expect(h.state().transport.phase).toBe("disconnected");
  h.controller.close();
});

it("does not start recovery while status is in flight or start probe/sampling writes during checking",async()=>{
  const slowStatus=deferred<ApiResult<MonitorStatus>>();
  const status=vi.fn().mockResolvedValueOnce(ok(statusResult())).mockImplementationOnce(()=>slowStatus.promise)
    .mockResolvedValueOnce(ok(statusResult()));
  const h=harness(status);await h.controller.loadInitial();h.sockets[0]!.handlers.onClosed();
  const reading=h.controller.refreshStatus();
  await h.controller.reconnectLive();
  expect(status).toHaveBeenCalledTimes(2);
  slowStatus.resolve(ok(statusResult()));await reading;
  const checking=deferred<ApiResult<MonitorStatus>>();
  status.mockImplementationOnce(()=>checking.promise);
  const recovery=h.controller.reconnectLive();
  await h.controller.refreshStatus();
  await h.controller.connectProbe("probe-1");
  await h.controller.startSampling("group",1n);
  expect(h.api.connect).not.toHaveBeenCalled();
  expect(h.api.start).not.toHaveBeenCalled();
  expect(status).toHaveBeenCalledTimes(3);
  h.controller.cancelLiveReconnect();checking.resolve(failed("MONITOR_AUTH_REQUIRED"));await recovery;
  expect(h.state().blockingError).toBeNull();
  h.controller.close();
});

it("blocks on a real recovery authentication failure without opening another socket",async()=>{
  const status=vi.fn().mockResolvedValueOnce(ok(statusResult())).mockResolvedValueOnce(failed("MONITOR_AUTH_REQUIRED"));
  const h=harness(status);await h.controller.loadInitial();h.sockets[0]!.handlers.onClosed();
  await h.controller.reconnectLive();
  expect(h.state().blockingError?.code).toBe("MONITOR_AUTH_REQUIRED");
  expect(h.sockets).toHaveLength(1);
  h.controller.close();
});

it("rejects a cross-session live state without applying it to the retained workbench",async()=>{
  const h=harness();await h.controller.loadInitial();h.sockets[0]!.handlers.onOpen();
  const other={...statusResult(),project:{...statusResult().project,logicalProjectId:"other-project"}};
  h.sockets[0]!.handlers.onEnvelope({event:{eventId:1n,type:"state",data:{stateRevision:1n,gap:false,status:other}},subscriberDropped:0n});
  expect(h.state().blockingError?.code).toBe("MONITOR_SESSION_EXPIRED");
  expect(h.state().status?.project.logicalProjectId).toBe("project");
  expect(h.sockets[0]!.close).toHaveBeenCalledTimes(1);
  h.controller.close();
});

it("does not allow a separate status refresh to migrate the saved workbench identity",async()=>{
  const next={...statusResult(),sessionId:"other-session"};
  const status=vi.fn().mockResolvedValueOnce(ok(statusResult())).mockResolvedValueOnce(ok(next));
  const h=harness(status);await h.controller.loadInitial();h.sockets[0]!.handlers.onOpen();
  await h.controller.refreshStatus();
  expect(h.state().blockingError?.code).toBe("MONITOR_SESSION_EXPIRED");
  expect(h.state().status?.sessionId).toBe("session");
  expect(h.sockets[0]!.close).toHaveBeenCalledTimes(1);
  h.controller.close();
});

it("does not replay a successful sampling write when its following GET loses to live state",async()=>{
  const slow=deferred<ApiResult<MonitorStatus>>();
  const status=vi.fn().mockResolvedValueOnce(ok(statusResult())).mockImplementationOnce(()=>slow.promise);
  const h=harness(status);await h.controller.loadInitial();h.sockets[0]!.handlers.onOpen();
  vi.mocked(h.api.start).mockResolvedValue(ok({groupId:"group",groupRevision:1n,runId:"run",intervalMs:250}));
  const writing=h.controller.startSampling("group",1n);
  await Promise.resolve();
  const newer={...statusResult(),sampling:{...statusResult().sampling,bindingEpoch:2n,runId:"new-run"}};
  h.sockets[0]!.handlers.onEnvelope({event:{eventId:1n,type:"state",data:{stateRevision:2n,gap:false,status:newer}},subscriberDropped:0n});
  slow.resolve(ok(statusResult()));await writing;
  expect(h.api.start).toHaveBeenCalledTimes(1);
  expect(h.state().status?.sampling.runId).toBe("new-run");
  expect(h.state().failures["sampling.start"]).toBeUndefined();
  h.controller.close();
});
