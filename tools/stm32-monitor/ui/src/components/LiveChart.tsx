import type {JSX} from "preact";
import {useEffect,useRef} from "preact/hooks";
import * as echarts from "echarts/core";
import type {DisplaySeries} from "../state/model";
import type {ZoomRange} from "../chart/zoom";
import {buildChartOption} from "../chart/echarts";

export type LiveChartProps={
  series:readonly DisplaySeries[];
  range:ZoomRange;
  onZoom:(range:ZoomRange)=>void|Promise<void>;
};

export function LiveChart({series,range}:LiveChartProps):JSX.Element{
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
    return()=>{chart?.dispose();chartRef.current=null;};
  },[]);
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
  return<section className="panel" aria-label="Live chart">
    <h2>Live chart</h2>
    <div ref={hostRef} style={{width:"100%",height:280}} role="img" aria-label="Live value chart"/>
  </section>;
}
