import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import {LiveChart} from "../src/components/LiveChart";
import {buildChartOption} from "../src/chart/echarts";

const chart=vi.hoisted(()=>({setOption:vi.fn(),on:vi.fn(),off:vi.fn(),resize:vi.fn(),dispose:vi.fn()}));
vi.mock("echarts/core",()=>({init:vi.fn(()=>chart),use:vi.fn()}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));
beforeEach(()=>vi.clearAllMocks());
afterEach(()=>vi.unstubAllGlobals());

it("resizes the existing chart when workbench space changes",()=>{
  const frames:FrameRequestCallback[]=[];
  vi.stubGlobal("requestAnimationFrame",(callback:FrameRequestCallback)=>{frames.push(callback);return frames.length;});
  vi.stubGlobal("cancelAnimationFrame",vi.fn());
  const view=render(<LiveChart series={[]} range={{start:0,end:100}} onZoom={vi.fn()} layoutKey="directory-open"/>);
  frames.shift()?.(0);
  const before=chart.resize.mock.calls.length;
  view.rerender(<LiveChart series={[]} range={{start:0,end:100}} onZoom={vi.fn()} layoutKey="directory-closed"/>);
  frames.shift()?.(0);
  expect(chart.resize).toHaveBeenCalledTimes(before+1);
  view.unmount();
});

it("feeds chart gestures into the latest zoom callback without setOption loops or late unmount effects",()=>{
  const first=vi.fn(),second=vi.fn();
  const view=render(<LiveChart series={[]} range={{start:0,end:100}} onZoom={first}/>);
  expect(chart.on).toHaveBeenCalledWith("datazoom",expect.any(Function));
  const emit=chart.on.mock.calls.find(call=>call[0]==="datazoom")![1] as (event:unknown)=>void;
  emit({start:20,end:80});
  expect(first).toHaveBeenCalledExactlyOnceWith({start:20,end:80});
  view.rerender(<LiveChart series={[]} range={{start:20,end:80}} onZoom={second}/>);
  const option=chart.setOption.mock.lastCall?.[0] as {dataZoom:readonly {start:number;end:number}[]};
  expect(option.dataZoom[0]).toMatchObject({start:20,end:80});
  expect(chart.setOption.mock.lastCall?.[1]).toMatchObject({silent:true});
  emit({start:20,end:80});
  expect(second).not.toHaveBeenCalled();
  emit({batch:[{start:Number.NaN,end:70},{start:30,end:70},{start:40,end:60}]});
  expect(second).toHaveBeenCalledExactlyOnceWith({start:30,end:70});
  const growing=[{key:"variable:x",label:"x",points:[
    {capturedUnixNs:1n,capturedAtUtc:"t1",value:1,segment:0n},
  ]}];
  view.rerender(<LiveChart series={growing} range={{start:30,end:70}} onZoom={second} visible={false}/>);
  expect((chart.setOption.mock.lastCall?.[0] as {dataZoom:readonly {start:number;end:number}[]}).dataZoom[0])
    .toMatchObject({start:30,end:70});
  view.rerender(<LiveChart series={growing} range={{start:30,end:70}} onZoom={second} visible/>);
  emit({start:80,end:20,batch:[{start:40,end:60}]});
  expect(second).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(chart.off).toHaveBeenCalledWith("datazoom",emit);
  expect(chart.dispose).toHaveBeenCalledTimes(1);
  emit({start:40,end:60});
  expect(second).toHaveBeenCalledTimes(1);
});

it("distinguishes no selection, selected without samples, and real timestamps with only missing values",()=>{
  const view=render(<LiveChart series={[]} range={{start:0,end:100}} onZoom={vi.fn()}/>);
  expect(screen.getByText("选择曲线后显示波形。")).toBeTruthy();
  view.rerender(<LiveChart series={[{key:"variable:x",label:"x",points:[]}]}
    range={{start:0,end:100}} onZoom={vi.fn()}/>);
  expect(screen.getByText("已选择曲线，等待采样数据。")).toBeTruthy();
  view.rerender(<LiveChart series={[{key:"variable:x",label:"x",points:[
    {capturedUnixNs:1n,capturedAtUtc:"2026-10-15T00:00:00Z",value:null,segment:0n},
  ]}]} range={{start:0,end:100}} onZoom={vi.fn()}/>);
  expect(screen.getByText("已有采集时间，但暂无可绘制的数值。")).toBeTruthy();
  expect(screen.getByText("起点（UTC）：2026-10-15T00:00:00Z")).toBeTruthy();
  view.unmount();
});

it("shows each original UTC and nanosecond value as text in the tooltip",()=>{
  const label="<img src=x onerror=alert(1)>";
  const option=buildChartOption([{key:"variable:unsafe",label,points:[
    {capturedUnixNs:1_234_567_890n,capturedAtUtc:"2026-10-15T00:00:01.234567890Z",value:42,segment:0n},
  ]}],{start:0,end:100});
  const entry=(option.series as readonly {data:readonly unknown[]}[])[0]!.data[0];
  const formatter=(option.tooltip as {formatter:(params:unknown)=>HTMLElement}).formatter;
  const content=formatter([{seriesName:label,data:entry}]);
  expect(content.textContent).toContain(label);
  expect(content.textContent).toContain("2026-10-15T00:00:01.234567890Z");
  expect(content.textContent).toContain("1234567890");
  expect(content.textContent).toContain("42");
  expect(content.querySelector("img")).toBeNull();
});

it("omits gap and malformed tooltip entries while describing a sampled missing value",()=>{
  const option=buildChartOption([{key:"variable:x",label:"x",points:[
    {capturedUnixNs:1_000_000n,capturedAtUtc:"2026-10-15T00:00:00Z",value:null,segment:0n},
    {capturedUnixNs:2_000_000n,capturedAtUtc:"",value:null,segment:0n},
  ]}],{start:0,end:100});
  const formatter=(option.tooltip as {formatter:(params:unknown)=>HTMLElement}).formatter;
  const first=(option.series as readonly {data:readonly unknown[]}[])[0]!.data[0];
  const content=formatter([{seriesName:"x",data:null},{seriesName:"x",data:{value:[1,null],capturedAtUtc:"",capturedUnixNs:""}},
    {seriesName:"x",data:first}]);
  expect(content.textContent).toContain("读取空缺");
  expect(content.textContent).toContain("2026-10-15T00:00:00Z");
  expect(content.children).toHaveLength(1);
});

it("ignores malformed chart gestures and accepts a later valid batch gesture",()=>{
  const onZoom=vi.fn();
  const view=render(<LiveChart series={[]} range={{start:0,end:100}} onZoom={onZoom}/>);
  const emit=chart.on.mock.calls.find(call=>call[0]==="datazoom")![1] as (event:unknown)=>void;
  emit(null);
  emit({start:"10",end:50});
  emit({batch:[null,{start:"30",end:70}]});
  expect(onZoom).not.toHaveBeenCalled();
  emit({batch:[null,{start:15,end:75}]});
  expect(onZoom).toHaveBeenCalledExactlyOnceWith({start:15,end:75});
  view.unmount();
});
