// @vitest-environment node
import {expect,it} from "vitest";
import {buildChartOption,projectChart} from "../src/chart/echarts";
import type {DisplaySeries} from "../src/state/model";

const point=(capturedUnixNs:bigint,capturedAtUtc:string,value:number|null,segment=0n)=>
  ({capturedUnixNs,capturedAtUtc,value,segment});
const line=(key:string,points:DisplaySeries["points"]):DisplaySeries=>({key,label:key,points});
type Datum={value:[number,number|null];capturedAtUtc:string;capturedUnixNs:string};
const data=(option:ReturnType<typeof buildChartOption>)=>option.series as readonly {id:string;data:readonly Datum[]}[];

it("plots a late-selected curve at each point's own time on one value axis",()=>{
  const option=buildChartOption([
    line("variable:A",[point(1_000_000_000n,"A0",1),point(3_000_000_000n,"A2",3)]),
    line("variable:B",[point(2_500_000_000n,"B1.5",9)]),
  ],{start:0,end:100});
  expect(option.xAxis).toMatchObject({type:"value",min:0,max:2000});
  expect(data(option)[0]?.data.map(item=>item.value)).toEqual([[0,1],[2000,3]]);
  expect(data(option)[1]?.data.map(item=>item.value)).toEqual([[1500,9]]);
  expect(data(option)[1]?.id).toBe("variable:B");
  expect(data(option)[1]?.data[0]).toMatchObject({capturedAtUtc:"B1.5",capturedUnixNs:"2500000000"});
});

it("keeps real nulls and duplicate times but anchors artificial gaps without a 1970 axis",()=>{
  const option=buildChartOption([line("variable:A",[
    point(0n,"",null,1n),
    point(10_000_000_000n,"UTC10",2,1n),
    point(10_000_000_000n,"UTC10-duplicate",3,1n),
    point(0n,"",null,2n),
    point(12_000_000_000n,"UTC12",null,2n),
    point(13_000_000_000n,"UTC13",4,3n),
  ])],{start:0,end:100});
  const entries=data(option)[0]?.data??[];
  expect(option.xAxis).toMatchObject({type:"value",min:0,max:3000});
  expect(entries.filter(item=>item.capturedAtUtc==="UTC10"||item.capturedAtUtc==="UTC10-duplicate")).toHaveLength(2);
  expect(entries.map(item=>item.value)).toEqual([[0,2],[0,3],[0,null],[2000,null],[3000,4]]);
  expect(entries[3]?.capturedUnixNs).toBe("12000000000");
});

it("keeps signed-int64 precision and finite axes for empty and single-point series",()=>{
  const low=-(1n<<63n),high=(1n<<63n)-1n;
  const wide=buildChartOption([line("variable:A",[
    point(low,"low",1),point(high,"high",2),
  ])],{start:0,end:100});
  const wideData=data(wide)[0]!.data;
  expect(wideData[0]!.value[0]).toBe(0);
  expect(wideData[1]!.value[0]).toBeCloseTo(18_446_744_073_709.55,1);
  expect(Number.isFinite(wideData[1]!.value[0])).toBe(true);
  for(const lines of [[],[line("variable:empty",[])],[line("variable:one",[point(77n,"one",null)])]]){
    const option=buildChartOption(lines,{start:0,end:100});
    const axis=option.xAxis as {min:number;max:number};
    expect(Number.isFinite(axis.min)&&Number.isFinite(axis.max)&&axis.max>axis.min).toBe(true);
  }
});

it("uses the actual domain for two samples less than a millisecond apart",()=>{
  const samples=line("variable:fast",[
    point(1_000_000_000n,"first",1),
    point(1_000_500_000n,"second",2),
  ]);
  const projection=projectChart([samples]);
  const option=buildChartOption([samples],{start:50,end:100});
  expect(projection.maxMilliseconds).toBe(0.5);
  expect(option.xAxis).toMatchObject({type:"value",min:0,max:0.5});
  expect(data(option)[0]?.data.map(item=>item.value)).toEqual([[0,1],[0.5,2]]);
});

it("uses a time-bearing null as the origin and breaks a new segment without rewriting samples",()=>{
  const points=Object.freeze([
    Object.freeze(point(100_000_000n,"missing at 100",null,0n)),
    Object.freeze(point(200_000_000n,"value at 200",2,0n)),
    Object.freeze(point(300_000_000n,"new segment",3,1n)),
  ]);
  const projection=projectChart([line("variable:A",points)]);
  expect(projection.originNs).toBe(100_000_000n);
  expect(projection.originUtc).toBe("missing at 100");
  expect(projection.series[0]?.data.map(item=>item.value)).toEqual([[0,null],[100,2],[100,null],[200,3]]);
  expect(points).toHaveLength(3);
  const onlyGap=buildChartOption([line("variable:gap",[point(0n,"",null,1n)])],{start:0,end:100});
  expect(onlyGap.xAxis).toMatchObject({type:"value",min:0,max:1});
  expect(data(onlyGap)[0]?.data).toEqual([]);
});

it("uses the same time domain regardless of series order and retains all eight bounded caches",()=>{
  const first=line("variable:first",[point(10_000_000n,"first",1),point(30_000_000n,"later",3)]);
  const second=line("variable:second",[point(5_000_000n,"earliest",2)]);
  const forward=projectChart([first,second]),reverse=projectChart([second,first]);
  expect(forward.originNs).toBe(5_000_000n);
  expect(reverse.originNs).toBe(forward.originNs);
  expect(reverse.maxMilliseconds).toBe(forward.maxMilliseconds);
  expect(new Map(forward.series.map(item=>[item.id,item.data.map(entry=>entry.value)])))
    .toEqual(new Map(reverse.series.map(item=>[item.id,item.data.map(entry=>entry.value)])));

  const bounded=Array.from({length:8},(_,curve)=>line(`variable:${curve}`,
    Object.freeze(Array.from({length:600},(_,index)=>point(BigInt(curve*600+index),`t${curve}-${index}`,index)))));
  const projected=projectChart(bounded);
  expect(projected.series).toHaveLength(8);
  for(const item of projected.series)expect(item.data).toHaveLength(600);
  for(const item of bounded)expect(item.points).toHaveLength(600);
});
