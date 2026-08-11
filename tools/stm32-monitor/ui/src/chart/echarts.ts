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
    legend:{type:"scroll"},
    grid:{left:48,right:16,top:32,bottom:40},
    xAxis:{type:"category",data:series[0]?.points.map(point=>point.capturedAtUtc)??[]},
    yAxis:{type:"value",scale:true},
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
