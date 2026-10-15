import type {JSX} from "preact";
import {minimumZoomWidth,type ZoomAction,type ZoomRange} from "../chart/zoom";
import {copy} from "../presentation/zh";

export type ChartZoomControlsProps={
  range:ZoomRange;
  onAction:(action:ZoomAction)=>void|Promise<void>;
};

export function ChartZoomControls({range,onAction}:ChartZoomControlsProps):JSX.Element{
  const width=range.end-range.start;
  return<section className="panel zoom-controls" aria-label={copy.zoomTitle}>
    <p>{copy.zoomRange}{range.start}%–{range.end}%</p>
    <button type="button" disabled={width<=minimumZoomWidth+1e-9} onClick={()=>void onAction({type:"zoom.in"})}>{copy.zoomIn}</button>
    <button type="button" disabled={width>=100-1e-9} onClick={()=>void onAction({type:"zoom.out"})}>{copy.zoomOut}</button>
    <button type="button" onClick={()=>void onAction({type:"zoom.reset"})}>{copy.zoomReset}</button>
  </section>;
}
