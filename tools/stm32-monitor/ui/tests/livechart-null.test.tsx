import {expect,it,vi,beforeEach} from "vitest";
import {cleanup} from "@testing-library/preact";

vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn()}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));

// Force the first useRef call (the host ref) to stay null so the
// `if(host===null)return;` guard branch is exercised.
let hostNull=false;
vi.mock("preact/hooks",async(importOriginal)=>{
  const actual=await importOriginal<typeof import("preact/hooks")>();
  return{
    ...actual,
    useRef:function<T>(this:unknown,initial:T){
      if(!hostNull)return actual.useRef(initial);
      const ref={current:null};
      Object.defineProperty(ref,"current",{get:()=>null,set:()=>{}});
      return ref as {current:T};
    },
  };
});

import {render} from "@testing-library/preact";
import {LiveChart} from "../src/components/LiveChart";

beforeEach(()=>{
  cleanup();
  hostNull=false;
});

it("renders a chart host normally",()=>{
  const onZoom=vi.fn();
  render(<LiveChart series={[]} range={{start:0,end:100}} onZoom={onZoom}/>);
  expect(document.querySelector('[aria-label="Live value chart"]')).not.toBeNull();
});

it("tolerates a null host ref in the mount effect",async()=>{
  hostNull=true;
  const onZoom=vi.fn();
  render(<LiveChart series={[]} range={{start:0,end:100}} onZoom={onZoom}/>);
  await Promise.resolve();
  expect(onZoom).not.toHaveBeenCalled();
});
