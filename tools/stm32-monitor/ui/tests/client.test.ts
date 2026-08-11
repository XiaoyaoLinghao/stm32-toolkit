import {describe,expect,it} from "vitest";
import {createMonitorApi} from "../src/api/client";
const response=(operation:string,data:string)=>new Response(`{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":true,"operation":"${operation}","code":"OK","message":"","data":${data},"details":{}}`);
describe("monitor HTTP adapter",()=>{
  it("uses a bodyless same-origin request for pause",async()=>{
    let init:RequestInit|undefined;
    const api=createMonitorApi(async(_input,request)=>{init=request;return new Response('{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":true,"operation":"monitor.sampling.pause","code":"OK","message":"","data":{"paused":true},"details":{}}');},"http://monitor.test");
    expect(await api.pause()).toEqual({ok:true,data:{paused:true}});
    expect(init).toMatchObject({method:"POST",credentials:"same-origin",headers:{Origin:"http://monitor.test"}});
    expect(init?.body).toBeUndefined();
  });
  it("wraps authorized group imports in the accepted request shape",async()=>{
    let init:RequestInit|undefined;
    const api=createMonitorApi(async(_input,request)=>{init=request;return response("monitor.groups.import","[]");},"http://monitor.test");
    await api.importGroups({schemaVersion:1,groups:[]});
    expect(init).toEqual({method:"POST",credentials:"same-origin",headers:{Origin:"http://monitor.test","Content-Type":"application/json"},body:'{"document":{"schemaVersion":1,"groups":[]},"authorized":true}'});
  });
  it("authorizes exports without rounding signed-int64 bounds",async()=>{
    let init:RequestInit|undefined;
    const api=createMonitorApi(async(_input,request)=>{init=request;return response("monitor.exports.create",'{"exportId":"export","format":"jsonl","sha256":"digest","bytes":1,"valueCount":2}');},"http://monitor.test");
    await api.createExport(-9223372036854775808n,9223372036854775807n,"jsonl");
    expect(init).toEqual({method:"POST",credentials:"same-origin",headers:{Origin:"http://monitor.test","Content-Type":"application/json"},body:'{"startNs":-9223372036854775808,"endNs":9223372036854775807,"format":"jsonl","authorized":true}'});
  });
});
