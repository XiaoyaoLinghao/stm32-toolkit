import type {JSX} from "preact";
import {useEffect,useRef} from "preact/hooks";
import * as echarts from "echarts/core";
import type {DisplaySeries} from "../state/model";
import {normalizeZoomRange,sameZoomRange,type ZoomRange} from "../chart/zoom";
import {buildChartOption,projectChart} from "../chart/echarts";
import {copy} from "../presentation/zh";

export type LiveChartProps={
  series:readonly DisplaySeries[];
  range:ZoomRange;
  onZoom:(range:ZoomRange)=>void|Promise<void>;
  visible?:boolean;
  layoutKey?:string;
  headerActions?:JSX.Element;
};

function eventZoom(event:unknown):ZoomRange|null{
  if(event===null||typeof event!=="object")return null;
  const value=event as {start?:unknown;end?:unknown;batch?:unknown};
  if("start" in value&&"end" in value)
    return typeof value.start==="number"&&typeof value.end==="number"
      ?normalizeZoomRange(value.start,value.end):null;
  if(!Array.isArray(value.batch))return null;
  for(const item of value.batch){
    if(item===null||typeof item!=="object")continue;
    const candidate=item as {start?:unknown;end?:unknown};
    if(typeof candidate.start!=="number"||typeof candidate.end!=="number")continue;
    const normalized=normalizeZoomRange(candidate.start,candidate.end);
    if(normalized!==null)return normalized;
  }
  return null;
}
export function LiveChart({series,range,onZoom,visible=true,layoutKey,headerActions}:LiveChartProps):JSX.Element{
  const hostRef=useRef<HTMLDivElement>(null);
  const chartRef=useRef<echarts.ECharts|null>(null);
  const rangeRef=useRef(range),onZoomRef=useRef(onZoom);
  rangeRef.current=range;onZoomRef.current=onZoom;
  useEffect(()=>{
    const host=hostRef.current;
    if(host===null)return;
    let active=true;
    let chart:echarts.ECharts|null=null;
    try{
      chart=echarts.init(host);
    }catch{
      chart=null;
    }
    chartRef.current=chart;
    const zoomHandler=(event:unknown)=>{
      if(!active)return;
      const next=eventZoom(event);
      if(next===null||sameZoomRange(rangeRef.current,next))return;
      rangeRef.current=next;
      void onZoomRef.current(next);
    };
    chart?.on("datazoom",zoomHandler);
    const observer=typeof ResizeObserver==="undefined"?null:new ResizeObserver(()=>{if(active)chart?.resize();});
    observer?.observe(host);
    return()=>{active=false;observer?.disconnect();chart?.off?.("datazoom",zoomHandler);chart?.dispose();chartRef.current=null;};
  },[]);
  useEffect(()=>{
    if(!visible||typeof requestAnimationFrame==="undefined")return;
    const frame=requestAnimationFrame(()=>chartRef.current?.resize());
    return()=>cancelAnimationFrame(frame);
  },[visible,layoutKey]);
  useEffect(()=>{
    const chart=chartRef.current;
    if(chart===null)return;
    const option=buildChartOption(series,range);
    const started=performance.now();
    chart.setOption(option,{notMerge:true,silent:true});
    const durationMs=performance.now()-started;
    window.dispatchEvent(new CustomEvent("stm32-monitor:chart-update",{detail:{durationMs}}));
    const realized=series.reduce((n,s)=>n+Math.min(s.points.length,600),0);
    hostRef.current!.setAttribute("data-chart-realized-points",String(realized));
  },[series,range]);
  const projection=projectChart(series);
  const hasValue=series.some(item=>item.points.some(point=>point.capturedAtUtc!==""&&point.value!==null));
  const empty=series.length===0?copy.chartEmpty:projection.originNs===null?copy.chartWaiting:hasValue?null:copy.chartNoValues;
  return<section className="panel chart-panel" aria-label={copy.chartTitle}>
    <div className="panel-heading chart-heading"><h2>{copy.chartTitle}</h2><span>{copy.chartLimit}</span>{headerActions}</div>
    <div ref={hostRef} className="chart-host" role="img" aria-label={copy.chartAria}/>
    {projection.originUtc!==null&&<p className="chart-origin">{copy.chartOrigin}{projection.originUtc}</p>}
    {empty!==null&&<p className="chart-empty">{empty}</p>}
  </section>;
}
