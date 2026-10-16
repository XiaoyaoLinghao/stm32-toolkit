import {describe,expect,it} from "vitest";
import {readFileSync} from "node:fs";
import {debugFirmwareBindingGuard,parseEnvelope,registerDescriptorGuard,sampleValueGuard,variableDescriptorGuard} from "../src/api/contract";
import {createMonitorApi} from "../src/api/client";
import {parseLiveEnvelope} from "../src/api/live";
import {encodeJson,parseLossless} from "../src/api/wire";
const envelope=(data:string)=>`{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":true,"operation":"monitor.live","code":"OK","message":"","data":${data},"details":{"subscriberDropped":9223372036854775807}}`;
type PythonFixture={connect:{data:Record<string,unknown>};reconnect:{data:Record<string,unknown>};sample:unknown};
const pythonFixture=():PythonFixture=>{
  const path=process.env.STM32_MONITOR_WIRE_FIXTURE;
  if(path===undefined)throw new Error("STM32_MONITOR_WIRE_FIXTURE is required");
  return JSON.parse(readFileSync(path,"utf8")) as PythonFixture;
};
describe("accepted-base lossless live envelope",()=>{
  it("keeps every identity and counter outside Number",()=>{
    const result=parseLiveEnvelope(envelope(`{"eventId":9223372036854775807,"type":"hello","data":{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","stateRevision":9223372036854775807}}`));
    expect(result.ok).toBe(true);
    if(result.ok){expect(result.data.event.eventId).toBe(9223372036854775807n);expect(result.data.subscriberDropped).toBe(9223372036854775807n);}
    expect(encodeJson({startNs:9223372036854775806n,endNs:9223372036854775807n})).toBe('{"startNs":9223372036854775806,"endNs":9223372036854775807}');
  });
  it("accepts descriptor integers beyond signed-int64 without rounding",()=>{
    const variable=variableDescriptorGuard(parseLossless('{"selector":"x","typeName":"u64","kind":"enum","byteSize":8,"signed":false,"encoding":null,"qualifiers":[],"aliases":[],"enumValues":[{"value":9223372036854775808,"name":"high"}],"elementCount":null,"elementKind":null,"memberNames":[]}'));
    const register=registerDescriptorGuard(parseLossless('{"selector":"R","sizeBits":64,"access":null,"readAction":null,"resetValue":18446744073709551615,"resetMask":18446744073709551615,"fields":[],"sampleable":true,"requiresAccessAcknowledgement":false}'));
    expect(variable.enumValues[0]?.value).toBe(9223372036854775808n);
    expect(register.resetValue).toBe(18446744073709551615n);
    expect(register.resetMask).toBe(18446744073709551615n);
    expect(()=>registerDescriptorGuard(parseLossless('{"selector":"R","sizeBits":64,"access":null,"readAction":null,"resetValue":-1,"resetMask":0,"fields":[],"sampleable":true,"requiresAccessAcknowledgement":false}'))).toThrow("expected nonnegative integer");
  });
  it("preserves own __proto__ typed JSON without inherited pollution",()=>{
    const sample=sampleValueGuard(parseLossless('{"watch":{"kind":"variable","expression":"x"},"status":"OK","typedValue":{"__proto__":{"polluted":true},"safe":1},"code":null,"definition":{"__proto__":{"definitionPolluted":true}}}'));
    expect(sample.status).toBe("OK");
    if(sample.status==="OK"){
      const typed=sample.typedValue as Record<string,unknown>;
      expect(Object.hasOwn(typed,"__proto__")).toBe(true);
      expect("polluted" in typed).toBe(false);
      expect(Object.getPrototypeOf(typed)).toBeNull();
    }
    const definition=sample.definition as Record<string,unknown>;
    expect(Object.hasOwn(definition,"__proto__")).toBe(true);
    expect("definitionPolluted" in definition).toBe(false);
    expect(Object.getPrototypeOf(definition)).toBeNull();
  });
  it("rejects inconsistent success and failure envelopes",()=>{
    const fields='"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","operation":"monitor.test","details":{}';
    const invalid=[
      `{${fields},"ok":true,"code":"OK","message":"not empty","data":null}`,
      `{${fields},"ok":false,"code":"MONITOR_TEST","message":"","data":null}`,
      `{${fields},"ok":false,"code":"MONITOR_TEST","message":"failed","data":{}}`,
    ];
    for(const text of invalid)expect(parseEnvelope(text,"monitor.test",()=>null)).toEqual({ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"});
  });
  it("consumes current Python connect and reconnect binding serializers",()=>{
    const fixture=pythonFixture();
    const connect=parseEnvelope(JSON.stringify(fixture.connect),"monitor.probe.connect",debugFirmwareBindingGuard);
    const reconnect=parseEnvelope(JSON.stringify(fixture.reconnect),"monitor.probe.reconnect",debugFirmwareBindingGuard);
    expect(connect.ok).toBe(true);
    expect(reconnect.ok).toBe(true);
    if(connect.ok){expect(connect.data.observationSessionId).toBe("observe");expect(connect.data.elfSize).toBe(4096);expect(connect.data.memoryRegions[0]?.origin).toBe(0x08000000);expect(connect.data.svdReadableRegions).toEqual([{name:"PERIPH",origin:0x40000000,length:0x1000,attributes:"r--"}]);}
    if(reconnect.ok)expect(reconnect.data.svdReadableRegions).toEqual(connect.ok?connect.data.svdReadableRegions:[]);
    const sample=sampleValueGuard(parseLossless(JSON.stringify(fixture.sample)));
    expect(sample.status).toBe("OK");
    if(sample.status==="OK")expect(sample.typedValue).toEqual({vendorShape:[1,{nested:true}]});
  });
  it("accepts current Python connect and reconnect responses through the HTTP adapter",async()=>{
    const fixture=pythonFixture(),requests:{url:string;init:RequestInit|undefined}[]=[];
    const api=createMonitorApi(async(input,init)=>{
      requests.push({url:String(input),init});
      return new Response(JSON.stringify(requests.length===1?fixture.connect:fixture.reconnect));
    },"http://monitor.test");
    const connected=await api.connect("probe"),reconnected=await api.reconnect();
    expect(connected.ok).toBe(true);
    expect(reconnected.ok).toBe(true);
    if(connected.ok&&reconnected.ok)expect(reconnected.data).toEqual(connected.data);
    expect(requests.map(request=>new URL(request.url).pathname)).toEqual(["/api/v1/probe/connect","/api/v1/probe/reconnect"]);
    expect(requests.map(request=>request.init?.method)).toEqual(["POST","POST"]);
  });
  it("rejects missing, empty, null, malformed and extra binding fields from Python responses",()=>{
    const fixture=pythonFixture(),base=fixture.connect.data;
    const absent={...base};delete absent.svdReadableRegions;
    const region=(base.svdReadableRegions as Record<string,unknown>[])[0];
    expect(region).toBeDefined();
    const invalid=[absent,{...base,svdReadableRegions:[]},{...base,svdReadableRegions:null},
      {...base,svdReadableRegions:{}},{...base,svdReadableRegions:[{...region,origin:"invalid"}]},
      {...base,svdReadableRegions:[{...region,unknown:true}]},{...base,unknown:true}];
    for(const {operation,response} of [{operation:"monitor.probe.connect",response:fixture.connect},{operation:"monitor.probe.reconnect",response:fixture.reconnect}])
      for(const data of invalid){
        const result=parseEnvelope(JSON.stringify({...response,data}),operation,debugFirmwareBindingGuard);
        expect(result).toEqual({ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"});
      }
  });
});
