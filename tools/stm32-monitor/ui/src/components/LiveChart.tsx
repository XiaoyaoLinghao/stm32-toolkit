import type {JSX} from "preact";
import {useEffect,useRef} from "preact/hooks";
import * as echarts from "echarts/core";
import type {DisplaySeries} from "../state/model";
import type {ZoomRange} from "../chart/zoom";
import {buildChartOption} from "../chart/echarts";
import {copy} from "../presentation/zh";

export type LiveChartProps={
  series:readonly DisplaySeries[];
  range:ZoomRange;
  onZoom:(range:ZoomRange)=>void|Promise<void>;
  visible?:boolean;
};

export function LiveChart({series,range,visible=true}:LiveChartProps):JSX.Element{
  const hostRef=useRef<HTMLDivElement>(null);
  const chartRef=useRef<echarts.ECharts|null>(null);
  useEffect(()=>{
    const host=hostRef.current;
    if(host===null)return;
    let chart:echarts.ECharts|null=null;
    try{
      chart=echarts.init(host);
    }catch{
      chart=null;
    }
    chartRef.current=chart;
    const observer=typeof ResizeObserver==="undefined"?null:new ResizeObserver(()=>chart?.resize());
    observer?.observe(host);
    return()=>{observer?.disconnect();chart?.dispose();chartRef.current=null;};
  },[]);
  useEffect(()=>{
    if(!visible||typeof requestAnimationFrame==="undefined")return;
    const frame=requestAnimationFrame(()=>chartRef.current?.resize());
    return()=>cancelAnimationFrame(frame);
  },[visible]);
  useEffect(()=>{
    const chart=chartRef.current;
    if(chart===null)return;
    const option=buildChartOption(series,range);
    const started=performance.now();
    chart.setOption(option,{notMerge:true});
    const durationMs=performance.now()-started;
    window.dispatchEvent(new CustomEvent("stm32-monitor:chart-update",{detail:{durationMs}}));
    const realized=series.reduce((n,s)=>n+Math.min(s.points.length,600),0);
    hostRef.current!.setAttribute("data-chart-realized-points",String(realized));
  },[series,range]);
  return<section className="panel chart-panel" aria-label={copy.chartTitle}>
    <div className="panel-heading"><h2>{copy.chartTitle}</h2><span>{copy.chartLimit}</span></div>
    <div ref={hostRef} className="chart-host" role="img" aria-label={copy.chartAria}/>
    {series.length===0&&<p className="chart-empty">{copy.chartEmpty}</p>}
  </section>;
}
