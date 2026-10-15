export type ZoomRange={start:number;end:number};
export type ZoomAction={type:"zoom.in"}|{type:"zoom.out"}|{type:"zoom.reset"}|{type:"zoom.set";start:number;end:number};
export const initialZoom:ZoomRange={start:0,end:100};
export const minimumZoomWidth=1;
const bounded=(value:number)=>Math.min(100,Math.max(0,value));
const centered=(center:number,width:number):ZoomRange=>{
 let start=center-width/2,end=center+width/2;
 if(start<0){end-=start;start=0;}
 if(end>100){start-=end-100;end=100;}
 return{start:bounded(start),end:bounded(end)};
};
export const sameZoomRange=(left:ZoomRange,right:ZoomRange):boolean=>
 Math.abs(left.start-right.start)<1e-9&&Math.abs(left.end-right.end)<1e-9;
export function normalizeZoomRange(start:number,end:number):ZoomRange|null{
 if(!Number.isFinite(start)||!Number.isFinite(end)||start>=end)return null;
 const low=bounded(start),high=bounded(end);
 if(low>=high)return null;
 const width=high-low;
 return width<minimumZoomWidth?centered((low+high)/2,minimumZoomWidth):{start:low,end:high};
}
export function zoomReducer(range:ZoomRange,action:ZoomAction):ZoomRange{
 if(action.type==="zoom.reset")return sameZoomRange(range,initialZoom)?range:initialZoom;
 if(action.type==="zoom.in"||action.type==="zoom.out"){
  const width=range.end-range.start;
  const nextWidth=action.type==="zoom.in"?Math.max(minimumZoomWidth,width-20):Math.min(100,width+20);
  if(nextWidth===width)return range;
  const next=centered((range.start+range.end)/2,nextWidth);
  return sameZoomRange(range,next)?range:next;
 }
 const next=normalizeZoomRange(action.start,action.end);
 return next===null||sameZoomRange(range,next)?range:next;
}
