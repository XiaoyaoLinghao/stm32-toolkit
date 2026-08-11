import {describe,expect,it} from "vitest";
import {liveUrl,openLive} from "../src/api/live";
describe("monitor live adapter",()=>{
  it("replays the exact decimal event identifier and never sends a message",()=>{
    const sockets:{url:string;sent:boolean;close():void;onmessage:null|((event:MessageEvent<string>)=>void);onclose:null|(()=>void)}[]=[];
    const stop=openLive("https://monitor.test",9223372036854775807n,{onEnvelope:()=>undefined,onClosed:()=>undefined},url=>{const socket={url,sent:false,close(){},onmessage:null,onclose:null};sockets.push(socket);return socket as unknown as WebSocket;});
    expect(liveUrl("https://monitor.test",9223372036854775807n)).toBe("wss://monitor.test/api/v1/live?afterEventId=9223372036854775807");
    expect(sockets[0]?.sent).toBe(false);stop();
  });
});
