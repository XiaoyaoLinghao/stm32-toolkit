// @vitest-environment node
import {describe,expect,it} from "vitest";
import * as echarts from "echarts/core";
import {SVGRenderer} from "echarts/renderers";
import type {DisplaySeries} from "../src/state/model";
import {buildChartOption} from "../src/chart/echarts";

const point=(capturedAtUtc:string,value:number|null)=>({capturedAtUtc,capturedUnixNs:0n,value,segment:0n});
const series=(key:string,points:readonly{value:number|null;capturedAtUtc:string;capturedUnixNs:bigint;segment:bigint}[]):DisplaySeries=>({key,label:key,points});

describe("buildChartOption",()=>{
  it("produces category xAxis data and line series for each display series",()=>{
    const option=buildChartOption([
      series("variable:x",[point("t1",1),point("t2",null)]),
      series("register:r",[point("t1",2)]),
    ],{start:10,end:90});
    const xAxis=option.xAxis as {type:string;data:readonly string[]};
    expect(xAxis).toMatchObject({type:"category",data:["t1","t2"]});
    const optionSeries=option.series as readonly {data:readonly {value:number|null;itemName:string}[]}[];
    expect(optionSeries).toHaveLength(2);
    expect(optionSeries[0]?.data[0]?.value).toBe(1);
    expect(optionSeries[0]?.data[0]?.itemName).toBe("t1");
    expect(optionSeries[1]?.data[0]?.value).toBe(2);
    expect(option.dataZoom).toEqual([{type:"inside",start:10,end:90},{type:"slider",start:10,end:90}]);
  });
  it("falls back to an empty category when no series and maps null values",()=>{
    const option=buildChartOption([],{start:0,end:100});
    const xAxis=option.xAxis as {type:string;data:readonly string[]};
    expect(xAxis).toMatchObject({type:"category",data:[]});
    expect(option.series).toEqual([]);
  });
  it("preserves null point values as null data entries",()=>{
    const option=buildChartOption([series("variable:x",[point("t",null)])],{start:0,end:100});
    const data=(option.series as readonly {data:readonly {value:number|null}[]}[])[0]?.data;
    expect(data?.[0]?.value).toBeNull();
  });
  it("registers a working dataZoom window in the real ECharts engine",()=>{
    echarts.use([SVGRenderer]);
    const chart=echarts.init(null,null,{renderer:"svg",ssr:true,width:800,height:320});
    try{
      const points=Array.from({length:8},(_,index)=>point(`t${index}`,index));
      chart.setOption(buildChartOption([series("variable:x",points)],{start:50,end:100}),{notMerge:true});
      // ECharts keeps the processed data window behind its model API. Accessing
      // it here verifies the registered component actually filters the series.
      const model=(chart as unknown as {getModel:()=>{
        getComponent:(kind:string,index:number)=>unknown;
        getSeries:()=>{getData:()=>{count:()=>number}}[];
      }}).getModel();
      expect(model.getComponent("dataZoom",0)).toBeTruthy();
      expect(model.getSeries()[0]!.getData().count()).toBeLessThan(points.length);
    }finally{chart.dispose();}
  });
});
