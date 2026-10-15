import * as echarts from "echarts/core";
import {LineChart} from "echarts/charts";
import {GridComponent,TooltipComponent,LegendComponent,DataZoomComponent} from "echarts/components";
import {CanvasRenderer} from "echarts/renderers";
import type {EChartsCoreOption} from "echarts/core";
import type {DisplaySeries} from "../state/model";
import type {ZoomRange} from "./zoom";
import {copy} from "../presentation/zh";

echarts.use([LineChart,GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,CanvasRenderer]);

export type ChartDatum={value:[number,number|null];capturedAtUtc:string;capturedUnixNs:string};
export type ProjectedChartSeries={id:string;name:string;data:readonly ChartDatum[]};
export type ChartProjection={originNs:bigint|null;originUtc:string|null;maxMilliseconds:number;series:readonly ProjectedChartSeries[]};
const hasRealTime=(capturedAtUtc:string)=>capturedAtUtc!=="";
const millisecondsFrom=(capturedUnixNs:bigint,originNs:bigint):number=>{
  const difference=capturedUnixNs-originNs;
  return Number(difference/1_000_000n)+Number(difference%1_000_000n)/1_000_000;
};
export function projectChart(series:readonly DisplaySeries[]):ChartProjection{
  let originNs:bigint|null=null,latestNs:bigint|null=null,originUtc:string|null=null;
  for(const item of series)for(const point of item.points){
    if(!hasRealTime(point.capturedAtUtc))continue;
    if(originNs===null||point.capturedUnixNs<originNs){originNs=point.capturedUnixNs;originUtc=point.capturedAtUtc;}
    if(latestNs===null||point.capturedUnixNs>latestNs)latestNs=point.capturedUnixNs;
  }
  const projected=series.map(item=>{
    const data:ChartDatum[]=[];
    let previousX:number|null=null,previousSegment:bigint|null=null;
    for(const point of item.points){
      if(!hasRealTime(point.capturedAtUtc)){
        if(previousX!==null&&data.at(-1)?.value[1]!==null)
          data.push({value:[previousX,null],capturedAtUtc:"",capturedUnixNs:""});
        continue;
      }
      const x=millisecondsFrom(point.capturedUnixNs,originNs!);
      if(previousX!==null&&previousSegment!==point.segment&&data.at(-1)?.value[1]!==null)
        data.push({value:[previousX,null],capturedAtUtc:"",capturedUnixNs:""});
      data.push({value:[x,point.value],capturedAtUtc:point.capturedAtUtc,
        capturedUnixNs:point.capturedUnixNs.toString(10)});
      previousX=x;previousSegment=point.segment;
    }
    return{id:item.key,name:item.label,data};
  });
  const span=originNs===null||latestNs===null?0:millisecondsFrom(latestNs,originNs);
  return{originNs,originUtc,maxMilliseconds:Math.max(1,span),series:projected};
}
const chartDatum=(value:unknown):value is ChartDatum=>{
  if(value===null||typeof value!=="object")return false;
  const item=value as Partial<ChartDatum>;
  return Array.isArray(item.value)&&typeof item.capturedAtUtc==="string"&&typeof item.capturedUnixNs==="string";
};
function tooltipContent(params:unknown):string|HTMLElement{
  if(typeof document==="undefined")return "";
  const root=document.createElement("div");
  for(const param of Array.isArray(params)?params:[params]){
    const record=param as {seriesName?:unknown;data?:unknown};
    if(!chartDatum(record?.data)||record.data.capturedAtUtc==="")continue;
    const line=document.createElement("div");
    const value=record.data.value[1];
    line.textContent=`${String(record.seriesName??"")} · ${copy.historyCaptured} ${record.data.capturedAtUtc} · ${copy.value} ${value===null?copy.chartMissingValue:String(value)} · ${copy.rawNs} ${record.data.capturedUnixNs}`;
    root.appendChild(line);
  }
  return root;
}
export function buildChartOption(series:readonly DisplaySeries[],range:ZoomRange):EChartsCoreOption{
  const start=range.start,end=range.end;
  const projection=projectChart(series);
  return{
    color:["#2563eb","#0f9b8e","#e58a1f","#8b5cf6","#db5270","#137eaf","#ba7b1b","#537455"],
    textStyle:{fontFamily:"Segoe UI, Microsoft YaHei UI, Microsoft YaHei, sans-serif",color:"#536174"},
    legend:{type:"scroll",selectedMode:false,textStyle:{color:"#536174"}},
    grid:{left:56,right:20,top:32,bottom:74},
    xAxis:{type:"value",min:0,max:projection.maxMilliseconds,name:copy.chartTimeAxis,
      nameLocation:"middle",nameGap:28,axisLabel:{color:"#536174"}},
    yAxis:{type:"value",scale:true,axisLabel:{color:"#536174"}},
    dataZoom:[{type:"inside",start,end},{type:"slider",start,end}],
    tooltip:{trigger:"axis",renderMode:"html",formatter:tooltipContent},
    series:projection.series.map(item=>({
      id:item.id,name:item.name,type:"line",showSymbol:false,connectNulls:false,
      data:item.data,
    })),
  };
}
