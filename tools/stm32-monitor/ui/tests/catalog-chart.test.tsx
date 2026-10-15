import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {CatalogPanel} from "../src/components/CatalogPanel";
import {LiveChart} from "../src/components/LiveChart";
import {ChartZoomControls} from "../src/components/ChartZoomControls";
import type {VariableDescriptor,RegisterDescriptor} from "../src/api/contract";

vi.mock("echarts/core",()=>{
  const chart={setOption:vi.fn(),dispose:vi.fn(),on:vi.fn()};
  return{
    init:vi.fn(()=>chart),
    use:vi.fn(),
    default:{init:vi.fn(()=>chart),use:vi.fn()},
  };
});
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));

const variable:VariableDescriptor={selector:"counter",typeName:"int",kind:"int",byteSize:4,signed:true,encoding:null,
  qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]};

it("CatalogPanel searches variables and adds a watch",async()=>{
  const search=vi.fn(),add=vi.fn();
  render(<CatalogPanel connected bindingEpoch={3n}
    variables={{kind:"variables",query:"counter",bindingKey:"ws/s/p/3",cursor:null,items:[variable],nextCursor:null}}
    registers={null} onSearch={search} onNext={vi.fn()} onAdd={add}/>);
  await userEvent.type(screen.getByPlaceholderText("输入符号或寄存器前缀"),"counter");
  expect(search).toHaveBeenCalledWith("variables","counter");
  await userEvent.click(screen.getByRole("button",{name:"加入观测组草稿"}));
  expect(add).toHaveBeenCalledWith({kind:"variable",expression:"counter"});
});

it("CatalogPanel shows no-catalog message when disconnected",()=>{
  render(<CatalogPanel connected={false} bindingEpoch={0n} variables={null} registers={null}
    onSearch={vi.fn()} onNext={vi.fn()} onAdd={vi.fn()}/>);
  expect(screen.getByText("连接探针后可搜索目录。")).toBeTruthy();
});

it("CatalogPanel renders register descriptors",async()=>{
  const register:RegisterDescriptor={selector:"TIM2_CNT",sizeBits:32,access:"rw",readAction:null,
    resetValue:null,resetMask:null,fields:[],sampleable:true,requiresAccessAcknowledgement:false};
  const add=vi.fn();
  render(<CatalogPanel connected bindingEpoch={3n} variables={null}
    registers={{kind:"registers",query:"TIM2",bindingKey:"ws/s/p/3",cursor:null,items:[register],nextCursor:null}}
    onSearch={vi.fn()} onNext={vi.fn()} onAdd={add}/>);
  await userEvent.click(screen.getByRole("tab",{name:"寄存器"}));
  await userEvent.type(screen.getByPlaceholderText("输入符号或寄存器前缀"),"TIM2");
  await userEvent.click(screen.getByRole("button",{name:"加入观测组草稿"}));
  expect(add).toHaveBeenCalledWith({kind:"register",registerPath:"TIM2_CNT"});
});

it("LiveChart initializes and renders chart host",()=>{
  const onZoom=vi.fn();
  render(<LiveChart series={[]} range={{start:0,end:100}} onZoom={onZoom}/>);
  expect(screen.getByRole("img",{name:"实时数值波形图"})).toBeTruthy();
});

it("ChartZoomControls fires reset action",async()=>{
  const onAction=vi.fn();
  render(<ChartZoomControls range={{start:0,end:100}} onAction={onAction}/>);
  await userEvent.click(screen.getByRole("button",{name:"重置缩放"}));
  expect(onAction).toHaveBeenCalledWith({type:"zoom.reset"});
});
