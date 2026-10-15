// @vitest-environment node
import {describe,expect,it} from "vitest";
import * as echarts from "echarts/core";
import {SVGRenderer} from "echarts/renderers";
import type {DisplaySeries} from "../src/state/model";
import {buildChartOption} from "../src/chart/echarts";

const point=(capturedAtUtc:string,value:number|null,capturedUnixNs=0n)=>({capturedAtUtc,capturedUnixNs,value,segment:0n});
const series=(key:string,points:readonly{value:number|null;capturedAtUtc:string;capturedUnixNs:bigint;segment:bigint}[]):DisplaySeries=>({key,label:key,points});

describe("buildChartOption",()=>{
  it("uses real relative-time coordinates and line series for each display series",()=>{
    const option=buildChartOption([
      series("variable:x",[point("t1",1,1_000_000_000n),point("t2",null,2_000_000_000n)]),
      series("register:r",[point("t1",2,1_000_000_000n)]),
    ],{start:10,end:90});
    expect(option.xAxis).toMatchObject({type:"value",min:0,max:1000});
    const optionSeries=option.series as readonly {data:readonly {value:[number,number|null];capturedAtUtc:string}[]}[];
    expect(optionSeries).toHaveLength(2);
    expect(optionSeries[0]?.data[0]?.value).toEqual([0,1]);
    expect(optionSeries[0]?.data[1]?.value).toEqual([1000,null]);
    expect(optionSeries[0]?.data[0]?.capturedAtUtc).toBe("t1");
    expect(optionSeries[1]?.data[0]?.value).toEqual([0,2]);
    expect(option.dataZoom).toEqual([{type:"inside",start:10,end:90},{type:"slider",start:10,end:90}]);
  });
  it("uses a finite value axis when no series exists",()=>{
    const option=buildChartOption([],{start:0,end:100});
    expect(option.xAxis).toMatchObject({type:"value",min:0,max:1});
    expect(option.series).toEqual([]);
  });
  it("preserves null point values as null data entries",()=>{
    const option=buildChartOption([series("variable:x",[point("t",null)])],{start:0,end:100});
    const data=(option.series as readonly {data:readonly {value:[number,number|null]}[]}[])[0]?.data;
    expect(data?.[0]?.value).toEqual([0,null]);
  });
  it("registers a working dataZoom window in the real ECharts engine",()=>{
    echarts.use([SVGRenderer]);
    const chart=echarts.init(null,null,{renderer:"svg",ssr:true,width:800,height:320});
    try{
      const points=Array.from({length:8},(_,index)=>point(`t${index}`,index,BigInt(index)*1_000_000_000n));
      const later=Array.from({length:3},(_,index)=>point(`late${index}`,index+20,BigInt(index+4)*1_000_000_000n));
      const option=buildChartOption([series("variable:x",points),series("variable:late",later)],{start:50,end:100});
      const plotted=option.series as readonly {data:readonly {value:[number,number|null]}[]}[];
      expect(plotted[1]?.data[0]?.value).toEqual([4000,20]);
      chart.setOption(option,{notMerge:true});
      // ECharts keeps the processed data window behind its model API. Accessing
      // it here verifies the registered component actually filters the series.
      const model=(chart as unknown as {getModel:()=>{
        getComponent:(kind:string,index:number)=>unknown;
        getSeries:()=>{getData:()=>{count:()=>number}}[];
      }}).getModel();
      expect(model.getComponent("dataZoom",0)).toBeTruthy();
      expect(model.getSeries()).toHaveLength(2);
      expect(model.getSeries()[0]!.getData().count()).toBeLessThan(points.length);
    }finally{chart.dispose();}
  });
});
