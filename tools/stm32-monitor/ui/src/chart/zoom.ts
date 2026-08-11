export type ZoomRange={start:number;end:number};
export type ZoomAction={type:"zoom.in"}|{type:"zoom.out"}|{type:"zoom.reset"}|{type:"zoom.set";start:number;end:number};
export const initialZoom:ZoomRange={start:0,end:100};
const bounded=(value:number)=>Math.min(100,Math.max(0,value));
export function zoomReducer(range:ZoomRange,action:ZoomAction):ZoomRange{
 if(action.type==="zoom.reset")return initialZoom;
 if(action.type==="zoom.in")return zoomReducer(range,{type:"zoom.set",start:range.start+10,end:range.end-10});
 if(action.type==="zoom.out")return zoomReducer(range,{type:"zoom.set",start:range.start-10,end:range.end+10});
 const start=bounded(action.start),end=bounded(action.end);return end>start?{start,end}:initialZoom;
}
