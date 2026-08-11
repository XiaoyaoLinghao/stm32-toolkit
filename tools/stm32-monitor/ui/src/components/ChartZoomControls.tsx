import type {JSX} from "preact";
import type {ZoomAction,ZoomRange} from "../chart/zoom";

export type ChartZoomControlsProps={
  range:ZoomRange;
  onAction:(action:ZoomAction)=>void|Promise<void>;
};

export function ChartZoomControls({range,onAction}:ChartZoomControlsProps):JSX.Element{
  return<section className="panel" aria-label="Chart zoom">
    <p>Zoom: {range.start}%–{range.end}%</p>
    <button type="button" onClick={()=>void onAction({type:"zoom.in"})}>Zoom in</button>
    <button type="button" onClick={()=>void onAction({type:"zoom.out"})}>Zoom out</button>
    <button type="button" onClick={()=>void onAction({type:"zoom.reset"})}>Reset zoom</button>
  </section>;
}
