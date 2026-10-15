import type {JSX} from "preact";
import type {ZoomAction,ZoomRange} from "../chart/zoom";
import {copy} from "../presentation/zh";

export type ChartZoomControlsProps={
  range:ZoomRange;
  onAction:(action:ZoomAction)=>void|Promise<void>;
};

export function ChartZoomControls({range,onAction}:ChartZoomControlsProps):JSX.Element{
  return<section className="panel zoom-controls" aria-label={copy.zoomTitle}>
    <p>{copy.zoomRange}{range.start}%–{range.end}%</p>
    <button type="button" onClick={()=>void onAction({type:"zoom.in"})}>{copy.zoomIn}</button>
    <button type="button" onClick={()=>void onAction({type:"zoom.out"})}>{copy.zoomOut}</button>
    <button type="button" onClick={()=>void onAction({type:"zoom.reset"})}>{copy.zoomReset}</button>
  </section>;
}
