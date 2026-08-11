import {expect,it,vi} from "vitest";
import {createMonitorApi} from "../src/api/client";

it("rejects a non-exact origin at construction",()=>{
  expect(()=>createMonitorApi(vi.fn() as never,"http://monitor.test/extra")).toThrow("origin must be exact");
  expect(()=>createMonitorApi(vi.fn() as never,"http://monitor.test")).not.toThrow();
});

it("returns MONITOR_TRANSPORT_FAILED when fetch rejects",async()=>{
  const api=createMonitorApi(async()=>{throw new Error("network down");},"http://monitor.test");
  const result=await api.status();
  expect(result).toEqual({ok:false,code:"MONITOR_TRANSPORT_FAILED",message:"Monitor request failed"});
});

it("returns MONITOR_RESPONSE_INVALID for malformed response",async()=>{
  const api=createMonitorApi(async()=>new Response("not-json") ,"http://monitor.test");
  const result=await api.status();
  expect(result).toEqual({ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"});
});

it("downloadExport parses server filename and returns blob",async()=>{
  const api=createMonitorApi(async()=>new Response("data",{headers:{"Content-Disposition":'attachment; filename="export.csv"',"Content-Type":"text/csv"}}),"http://monitor.test");
  const result=await api.downloadExport("e1");
  expect(result.ok).toBe(true);
  if(result.ok){expect(result.filename).toBe("export.csv");expect(result.contentType).toBe("text/csv");}
});

it("downloadExport returns failure on non-ok response",async()=>{
  const api=createMonitorApi(async()=>new Response('{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":false,"operation":"monitor.exports.download","code":"EXPORT_GONE","message":"expired","data":null,"details":{}}',{status:404}),"http://monitor.test");
  const result=await api.downloadExport("e1");
  expect(result).toEqual({ok:false,code:"EXPORT_GONE",message:"expired"});
});

it("downloadExport rejects missing filename disposition",async()=>{
  const api=createMonitorApi(async()=>new Response("data"),"http://monitor.test");
  const result=await api.downloadExport("e1");
  expect(result).toEqual({ok:false,code:"MONITOR_DOWNLOAD_INVALID",message:"Download metadata is invalid"});
});

it("downloadExport falls back to application/octet-stream when Content-Type is absent",async()=>{
  const responseLike={
    ok:true,
    headers:{get:(name:string)=>name==="Content-Disposition"?'attachment; filename="export.csv"':null},
    blob:async()=>new Blob(["data"]),
  };
  const api=createMonitorApi(async()=>responseLike as unknown as Response,"http://monitor.test");
  const result=await api.downloadExport("e1");
  expect(result.ok).toBe(true);
  if(result.ok){expect(result.contentType).toBe("application/octet-stream");expect(result.filename).toBe("export.csv");}
});

it("downloadExport treats a successful envelope on a failed response as invalid",async()=>{
  const responseLike={
    ok:false,
    headers:{get:()=>null},
    text:async()=>'{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":true,"operation":"monitor.exports.download","code":"OK","message":"","data":null,"details":{}}',
  };
  const api=createMonitorApi(async()=>responseLike as unknown as Response,"http://monitor.test");
  const result=await api.downloadExport("e1");
  expect(result.ok).toBe(false);
  if(!result.ok)expect(result.code).toBe("MONITOR_RESPONSE_INVALID");
});

it("omits optional history query params when undefined",async()=>{
  let url="";
  const api=createMonitorApi(async(input)=>{url=String(input);return new Response('{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":true,"operation":"monitor.history.query","code":"OK","message":"","data":{"batches":[],"valueCount":0,"nextCursor":null,"serializedBytes":0},"details":{}}');},"http://monitor.test");
  await api.history({startNs:0n,endNs:0n});
  expect(url).toContain("startNs=0");
  expect(url).toContain("endNs=0");
  expect(url).not.toContain("cursor=");
  expect(url).not.toContain("runId=");
  expect(url).not.toContain("groupId=");
  expect(url).not.toContain("limit=");
});

it("encodes query params for history",async()=>{
  let url="";
  const api=createMonitorApi(async(input)=>{url=String(input);return new Response('{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":true,"operation":"monitor.history.query","code":"OK","message":"","data":{"batches":[],"valueCount":0,"nextCursor":null,"serializedBytes":0},"details":{}}');},"http://monitor.test");
  await api.history({startNs:1n,endNs:2n,limit:10,cursor:"abc"});
  expect(url).toContain("startNs=1");
  expect(url).toContain("endNs=2");
  expect(url).toContain("limit=10");
  expect(url).toContain("cursor=abc");
});
