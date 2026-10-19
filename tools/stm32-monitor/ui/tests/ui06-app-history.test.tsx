import {afterEach,expect,it,vi} from "vitest";
import {fireEvent,render,screen,waitFor} from "@testing-library/preact";
import {App} from "../src/app";
import {sourcePage} from "./fixtures";

vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn(),default:{init:vi.fn(()=>null),use:vi.fn()}}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));
let preparedApi:object|null=null;
vi.mock("../src/api/client",()=>({createMonitorApi:()=>preparedApi}));
vi.mock("../src/api/live",()=>({openLive:()=>()=>{}}));
afterEach(()=>{preparedApi=null;});
const ok=<T,>(data:T)=>({ok:true,data} as const);

it("shows ordinary history failure in OperationRegion and retries A without overwriting draft B or export range",async()=>{
  let finish!:(result:ReturnType<typeof ok<{batches:never[];valueCount:bigint;nextCursor:null;serializedBytes:bigint}>>)=>void;
  const retry=new Promise<ReturnType<typeof ok<{batches:never[];valueCount:bigint;nextCursor:null;serializedBytes:bigint}>>>(resolve=>{finish=resolve;});
  const history=vi.fn().mockResolvedValueOnce({ok:false,code:"HISTORY_DOWN",message:"query unavailable"}).mockReturnValueOnce(retry);
  preparedApi={
    status:vi.fn(async()=>ok({workspaceId:"workspace",sessionId:"session",project:{logicalProjectId:"project",name:"Project",targetDevice:"STM32F407VG"},firmware:null,probe:{connected:false,probeId:null},sampling:{state:"IDLE",active:false,blockedCode:null,groupId:null,groupRevision:null,runId:null,lastSequence:null,bindingEpoch:0n,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n},probeConnected:false,samplingActive:false})),
    probes:vi.fn(async()=>ok({probes:[]})),groups:vi.fn(async()=>ok({groups:[],nextCursor:null,revision:"0"})),history,
    sourceVariables:vi.fn(async()=>ok(sourcePage())),
  };
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  fireEvent.input(screen.getByLabelText("开始时间（UTC）"),{target:{value:"2026-08-10T00:00:00.000"}});
  fireEvent.input(screen.getByLabelText("结束时间（UTC）"),{target:{value:"2026-08-10T00:00:02.000"}});
  fireEvent.click(screen.getByRole("button",{name:"查询历史"}));
  fireEvent.click(await screen.findByRole("button",{name:"操作问题 1"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("HISTORY_DOWN");
  fireEvent.click(screen.getByRole("button",{name:"关闭诊断详情"}));
  fireEvent.input(screen.getByLabelText("开始时间（UTC）"),{target:{value:"2026-08-11T00:00:00.000"}});
  fireEvent.input(screen.getByLabelText("结束时间（UTC）"),{target:{value:"2026-08-11T00:00:02.000"}});
  fireEvent.click(screen.getByRole("button",{name:"操作问题 1"}));
  fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
  await waitFor(()=>expect(history).toHaveBeenCalledTimes(2));
  expect(history.mock.calls[1]?.[0]).toEqual(history.mock.calls[0]?.[0]);
  expect(screen.getByText(/正在查询范围（UTC）/)).toHaveTextContent("2026-08-10T00:00:00.000Z");
  finish(ok({batches:[],valueCount:0n,nextCursor:null,serializedBytes:0n}));
  await screen.findByText(/当前结果范围（UTC）/);
  expect(screen.getByLabelText("开始时间（UTC）")).toHaveValue("2026-08-11T00:00");
  expect(screen.getByLabelText("结束时间（UTC）")).toHaveValue("2026-08-11T00:00:02.000");
  await waitFor(()=>expect(screen.getByLabelText("导出开始时间（UTC）")).toHaveValue("2026-08-10T00:00"));
  expect(screen.getByLabelText("导出结束时间（UTC）")).toHaveValue("2026-08-10T00:00:02.000");
});
