import {describe,expect,it,vi} from "vitest";
import {liveUrl,openLive,parseLiveEnvelope} from "../src/api/live";

const helloEnvelope=`{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":true,"operation":"monitor.live","code":"OK","message":"","data":{"eventId":1,"type":"hello","data":{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","stateRevision":1}},"details":{"subscriberDropped":9223372036854775807}}`;

type FakeSocket={url:string;onmessage:null|((event:{data:unknown})=>void);onclose:null|((event:unknown)=>void);close:ReturnType<typeof vi.fn>};

function harness(url="https://monitor.test",afterEventId:bigint|null=null){
  const handlers={onEnvelope:vi.fn(),onClosed:vi.fn()};
  let socket:FakeSocket|undefined;
  const stop=openLive(url,afterEventId,handlers,fakeUrl=>{
    socket={url:fakeUrl,onmessage:null,onclose:null,close:vi.fn()};
    return socket as unknown as WebSocket;
  });
  if(socket===undefined)throw new Error("socketFactory was not invoked");
  return{handlers,stop,socket};
}

describe("parseLiveEnvelope",()=>{
  it("accepts a valid envelope and keeps subscriberDropped lossless",()=>{
    const result=parseLiveEnvelope(helloEnvelope);
    expect(result.ok).toBe(true);
    if(result.ok){
      expect(result.data.event.type).toBe("hello");
      expect(result.data.subscriberDropped).toBe(9223372036854775807n);
    }
  });
  it("rejects malformed text without throwing",()=>{
    expect(parseLiveEnvelope("not-json")).toEqual({ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"});
  });
});

describe("liveUrl",()=>{
  it("maps https to wss and http to ws",()=>{
    expect(liveUrl("https://m.test",null)).toBe("wss://m.test/api/v1/live");
    expect(liveUrl("http://m.test",null)).toBe("ws://m.test/api/v1/live");
  });
  it("appends afterEventId only when present",()=>{
    expect(liveUrl("https://m.test",9223372036854775807n)).toBe("wss://m.test/api/v1/live?afterEventId=9223372036854775807");
  });
});

describe("openLive",()=>{
  it("opens the derived url and streams a parsed envelope",()=>{
    const {handlers,socket,stop}=harness();
    expect(socket.url).toBe("wss://monitor.test/api/v1/live");
    socket.onmessage?.({data:helloEnvelope});
    expect(handlers.onEnvelope).toHaveBeenCalledTimes(1);
    expect(handlers.onEnvelope.mock.calls[0]?.[0]?.event.type).toBe("hello");
    stop();
    expect(socket.close).toHaveBeenCalledTimes(1);
  });
  it("skips non-string and unparseable messages",()=>{
    const {handlers,socket}=harness();
    socket.onmessage?.({data:42});
    socket.onmessage?.({data:"not-json"});
    expect(handlers.onEnvelope).not.toHaveBeenCalled();
  });
  it("invokes onClosed when the socket closes before stop and stop is idempotent",()=>{
    const {handlers,socket,stop}=harness();
    socket.onclose?.({});
    expect(handlers.onClosed).toHaveBeenCalledTimes(1);
    stop();
    stop();
    expect(socket.close).toHaveBeenCalledTimes(1);
  });
  it("ignores late messages and close events once stopped",()=>{
    const {handlers,socket,stop}=harness();
    const onmessage=socket.onmessage;
    const onclose=socket.onclose;
    stop();
    onmessage?.({data:helloEnvelope});
    onclose?.({});
    expect(handlers.onEnvelope).not.toHaveBeenCalled();
    expect(handlers.onClosed).not.toHaveBeenCalled();
  });
  it("falls back to the platform WebSocket constructor when no factory is supplied",()=>{
    const handlers={onEnvelope:vi.fn(),onClosed:vi.fn()};
    const stop=openLive("https://monitor.test",null,handlers);
    expect(typeof stop).toBe("function");
    stop();
  });
});
