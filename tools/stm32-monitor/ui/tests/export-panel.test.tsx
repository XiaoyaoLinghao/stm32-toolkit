import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {ExportPanel} from "../src/components/ExportPanel";

vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn()}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));

const range={startNs:0n,endNs:3000000000n};
const artifact={exportId:"e1",format:"csv" as const,sha256:"a".repeat(64),bytes:123n,valueCount:4n};

it("cancels the export confirmation dialog and returns focus",async()=>{
  const create=vi.fn();
  render(<ExportPanel range={range} artifact={null} failure={null} onCreate={create} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  const trigger=screen.getByRole("button",{name:"Create CSV export"});
  await userEvent.click(trigger);
  expect(screen.getByRole("dialog",{name:"Confirm history export"})).toBeTruthy();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog",{name:"Confirm history export"})).toBeNull();
  expect(create).not.toHaveBeenCalled();
});

it("cancels via the Cancel button without creating",async()=>{
  const create=vi.fn();
  render(<ExportPanel range={range} artifact={null} failure={null} onCreate={create} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  await userEvent.click(screen.getByRole("button",{name:"Create JSONL export"}));
  await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
  expect(screen.queryByRole("dialog",{name:"Confirm history export"})).toBeNull();
  expect(create).not.toHaveBeenCalled();
});

it("does not create export for an invalid inverted range",async()=>{
  const create=vi.fn();
  render(<ExportPanel range={range} artifact={null} failure={null} onCreate={create} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  const start=screen.getByLabelText("Export start"),end=screen.getByLabelText("Export end");
  await userEvent.clear(start);
  await userEvent.type(start,"2026-08-11T00:00:00.000");
  await userEvent.clear(end);
  await userEvent.type(end,"2026-08-10T00:00:00.000");
  await userEvent.click(screen.getByRole("button",{name:"Create JSONL export"}));
  await userEvent.click(screen.getByRole("button",{name:"Confirm export"}));
  expect(create).not.toHaveBeenCalled();
});

it("refreshes and downloads a verified artifact",async()=>{
  const refresh=vi.fn(),download=vi.fn();
  render(<ExportPanel range={range} artifact={artifact} failure={null} onCreate={vi.fn()} onRefresh={refresh} onDownload={download}/>);
  await userEvent.click(screen.getByRole("button",{name:"Refresh export status"}));
  expect(refresh).toHaveBeenCalledWith("e1");
  await userEvent.click(screen.getByRole("button",{name:"Download verified CSV"}));
  expect(download).toHaveBeenCalledWith("e1");
});

it("renders jsonl artifact download label",()=>{
  render(<ExportPanel range={range} artifact={{...artifact,format:"jsonl"}} failure={null} onCreate={vi.fn()} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  expect(screen.getByRole("button",{name:"Download verified JSONL"})).toBeTruthy();
});

it("renders public failure alert without leaking paths or AI controls",()=>{
  render(<ExportPanel range={range} artifact={null} failure={{ok:false,code:"MONITOR_EXPORT_FAILED",message:"history export failed"}} onCreate={vi.fn()} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("MONITOR_EXPORT_FAILED");
  expect(screen.queryByLabelText(/file name/i)).toBeNull();
  expect(screen.queryByText(/AI snapshot|diagnostic session/i)).toBeNull();
});
