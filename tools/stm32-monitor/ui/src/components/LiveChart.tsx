import type {JSX} from "preact";
import {useEffect,useRef} from "preact/hooks";
import * as echarts from "echarts/core";
import type {EChartsCoreOption} from "echarts/core";
import type {DisplaySeries} from "../state/model";
import type {ZoomRange} from "../chart/zoom";
import {buildChartOption} from "../chart/echarts";

export type LiveChartProps={
  series:readonly DisplaySeries[];
  range:ZoomRange;
  onZoom:(range:ZoomRange)=>void|Promise<void>;
};

export function LiveChart({series,range,onZoom}:LiveChartProps):JSX.Element{
  const hostRef=useRef<HTMLDivElement>(null);
  const chartRef=useRef<echarts.ECharts|null>(null);
  useEffect(()=>{
    if(hostRef.current===null)return;
    const chart=echarts.init(hostRef.current);
    chartRef.current=chart;
    return()=>{chart.dispose();chartRef.current=null;};
  },[]);
  useEffect(()=>{
    const chart=chartRef.current;
    if(chart===null)return;
    const option=buildChartOption(series,range);
    chart.setOption(option,{notMerge:true});
  },[series,range]);
  return<section className="panel" aria-label="Live chart">
    <h2>Live chart</h2>
    <div ref={hostRef} style={{width:"100%",height:280}} role="img" aria-label="Live value chart"/>
  </section>;
}
