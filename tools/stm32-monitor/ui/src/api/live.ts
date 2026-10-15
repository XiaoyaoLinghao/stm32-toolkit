import {envelopeDetails,i64,liveEventGuard,parseEnvelope,type ApiResult,type I64,type LiveHandlers,type ParsedLiveEnvelope} from "./contract";

export function parseLiveEnvelope(text:string):ApiResult<ParsedLiveEnvelope>{const result=parseEnvelope(text,"monitor.live",liveEventGuard);if(!result.ok)return result;try{return{ok:true,data:{event:result.data,subscriberDropped:i64(envelopeDetails(result).subscriberDropped)}};}catch{return{ok:false,code:"MONITOR_RESPONSE_INVALID",message:"Monitor response is invalid"};}}
export function liveUrl(origin:string,afterEventId:I64|null):string{const value=new URL("api/v1/live",origin+"/");value.protocol=value.protocol==="https:"?"wss:":"ws:";if(afterEventId!==null)value.searchParams.set("afterEventId",afterEventId.toString(10));return value.href;}
export function openLive(origin:string,afterEventId:I64|null,handlers:LiveHandlers,socketFactory:(url:string)=>WebSocket=(url)=>new WebSocket(url)):()=>void{
  const socket=socketFactory(liveUrl(origin,afterEventId));
  let stopped=false,settled=false,closedSocket=false;
  const detach=()=>{socket.onopen=null;socket.onmessage=null;socket.onerror=null;socket.onclose=null;};
  const closeSocket=()=>{if(closedSocket)return;closedSocket=true;socket.close();};
  socket.onopen=()=>{if(!stopped&&!settled)handlers.onOpen();};
  socket.onmessage=message=>{if(stopped||settled||typeof message.data!=="string")return;
    const result=parseLiveEnvelope(message.data);if(result.ok)handlers.onEnvelope(result.data);};
  socket.onerror=()=>{if(stopped||settled)return;settled=true;detach();handlers.onFailed();closeSocket();};
  socket.onclose=()=>{if(stopped||settled)return;settled=true;detach();handlers.onClosed();};
  return()=>{if(stopped)return;stopped=true;detach();closeSocket();};
}
