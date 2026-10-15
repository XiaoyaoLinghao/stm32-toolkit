import {expect,it,vi} from "vitest";
import type {ApiResult,HistoryPage,HistoryQuery,MonitorApi} from "../src/api/contract";
import {createController} from "../src/controller";
import type {MonitorAction,MonitorState} from "../src/state/model";
import {initialState,reducer} from "../src/state/reducer";

const empty:HistoryPage={batches:[],valueCount:0n,nextCursor:null,serializedBytes:0n};
const queryA:HistoryQuery={startNs:10n,endNs:20n,runId:"run-a",groupId:"group-a",limit:25,cursor:"cursor-a"};
const queryB:HistoryQuery={startNs:30n,endNs:40n,runId:"run-b"};
const deferred=()=>{let resolve!:(value:ApiResult<HistoryPage>)=>void;const promise=new Promise<ApiResult<HistoryPage>>(done=>{resolve=done;});return{promise,resolve};};
function harness(history:MonitorApi["history"]){
  let state:MonitorState=initialState;
  const dispatch=(action:MonitorAction)=>{state=reducer(state,action);};
  const controller=createController({history} as MonitorApi,dispatch,()=>state);
  return{controller,state:()=>state,dispatch};
}

it("replaces in-flight context for explicit latest-wins and ignores the older completion",async()=>{
  const first=deferred(),second=deferred();
  const history=vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const h=harness(history);
  const old=h.controller.loadHistory(queryA);
  const oldId=h.state().history.inFlight?.requestId;
  expect(h.state().history.inFlight?.query).toEqual(queryA);
  const newer=h.controller.loadHistory(queryB);
  expect(h.state().history.inFlight?.requestId).not.toBe(oldId);
  expect(h.state().history.inFlight?.query).toEqual(queryB);
  first.resolve({ok:true,data:empty});await old;
  expect(h.state().history.inFlight?.query).toEqual(queryB);
  expect(h.state().history.query).toBeNull();
  second.resolve({ok:true,data:empty});await newer;
  expect(h.state().history.inFlight).toBeNull();
  expect(h.state().history.query).toEqual(queryB);
  h.controller.close();
});

it("retries an immutable failed cursor query with a new in-flight ID and advances only after success",async()=>{
  const again=deferred();
  const history=vi.fn().mockResolvedValueOnce({ok:false,code:"HISTORY_DOWN",message:"down"}).mockReturnValueOnce(again.promise);
  const h=harness(history);
  h.dispatch({type:"history.loaded",query:{startNs:10n,endNs:20n},page:{...empty,nextCursor:"cursor-a"}});
  await h.controller.nextHistory("cursor-a");
  const failedId=h.state().failures.history?.requestId;
  expect(h.state().history.inFlight).toBeNull();
  expect(h.state().history.cursorStack).toEqual([]);
  const retry=h.controller.retry("history",failedId!);
  expect(h.state().history.inFlight?.requestId).not.toBe(failedId);
  expect(h.state().history.inFlight?.query).toEqual({startNs:10n,endNs:20n,cursor:"cursor-a"});
  expect(h.state().history.inFlight?.navigation).toBe("next");
  expect(h.state().history.cursorStack).toEqual([]);
  again.resolve({ok:true,data:empty});await retry;
  expect(history).toHaveBeenCalledTimes(2);
  expect(history.mock.calls[1]?.[0]).toEqual(history.mock.calls[0]?.[0]);
  expect(h.state().history.inFlight).toBeNull();
  expect(h.state().history.cursorStack).toEqual([undefined]);
  h.controller.close();
});

it("does not clear a newer history context when an older ID is retired or fails",()=>{
  const h=harness(vi.fn());
  h.dispatch({type:"request.started",scope:"history",requestId:41n,historyContext:{query:queryA,navigation:"next"}});
  h.dispatch({type:"request.started",scope:"history",requestId:42n,historyContext:{query:queryB,navigation:"replace"}});
  h.dispatch({type:"request.retired",scope:"history",requestId:41n});
  h.dispatch({type:"request.failed",scope:"history",requestId:41n,code:"OLD",message:"old"});
  expect(h.state().history.inFlight).toEqual({requestId:42n,query:queryB,navigation:"replace"});
  expect(h.state().pending.history?.requestId).toBe(42n);
  h.controller.close();
});
