import * as echarts from "echarts/core";
import {LineChart} from "echarts/charts";
import {GridComponent,TooltipComponent,LegendComponent} from "echarts/components";
import {CanvasRenderer} from "echarts/renderers";
import type {EChartsCoreOption} from "echarts/core";
import type {DisplaySeries} from "../state/model";
import type {ZoomRange} from "./zoom";

echarts.use([LineChart,GridComponent,TooltipComponent,LegendComponent,CanvasRenderer]);

export function buildChartOption(series:readonly DisplaySeries[],range:ZoomRange):EChartsCoreOption{
  const start=range.start,end=range.end;
  return{
    color:["#2563eb","#0f9b8e","#e58a1f","#8b5cf6","#db5270","#137eaf","#ba7b1b","#537455"],
    textStyle:{fontFamily:"Segoe UI, Microsoft YaHei UI, Microsoft YaHei, sans-serif",color:"#536174"},
    legend:{type:"scroll",textStyle:{color:"#536174"}},
    grid:{left:48,right:16,top:32,bottom:40},
    xAxis:{type:"category",data:series[0]?.points.map(point=>point.capturedAtUtc)??[],axisLabel:{color:"#536174"}},
    yAxis:{type:"value",scale:true,axisLabel:{color:"#536174"}},
    dataZoom:[{type:"inside",start,end},{type:"slider",start,end}],
    tooltip:{trigger:"axis"},
    series:series.map(item=>({
      name:item.key,type:"line",showSymbol:false,connectNulls:false,
      data:item.points.map(point=>({
        value:point.value===null?null:point.value,
        itemName:point.capturedAtUtc,
      })),
    })),
  };
}
