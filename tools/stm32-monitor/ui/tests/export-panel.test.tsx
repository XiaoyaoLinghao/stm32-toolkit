import {expect,it,vi} from "vitest";
import {fireEvent,render,screen,waitFor} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {ExportPanel} from "../src/components/ExportPanel";

vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn()}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));

const range={startNs:0n,endNs:3000000000n};
const artifact={exportId:"e1",format:"csv" as const,sha256:"a".repeat(64),bytes:123n,valueCount:4n};

it("cancels the export confirmation dialog and returns focus",async()=>{
  const create=vi.fn();
  render(<ExportPanel range={range} artifact={null} failure={null} onCreate={create} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  const trigger=screen.getByRole("button",{name:"创建 CSV 导出"});
  await userEvent.click(trigger);
  expect(screen.getByRole("dialog",{name:"确认历史导出"})).toBeTruthy();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog",{name:"确认历史导出"})).toBeNull();
  await waitFor(()=>expect(trigger).toHaveFocus());
  expect(create).not.toHaveBeenCalled();
});

it("cancels via the Cancel button without creating",async()=>{
  const create=vi.fn();
  render(<ExportPanel range={range} artifact={null} failure={null} onCreate={create} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  const trigger=screen.getByRole("button",{name:"创建 JSONL 导出"});
  await userEvent.click(trigger);
  await userEvent.click(screen.getByRole("button",{name:"取消"}));
  expect(screen.queryByRole("dialog",{name:"确认历史导出"})).toBeNull();
  await waitFor(()=>expect(trigger).toHaveFocus());
  expect(create).not.toHaveBeenCalled();
});

it("traps Tab in the export dialog and restores an enabled field after confirmation",async()=>{
  render(<ExportPanel range={range} artifact={null} failure={null} onCreate={vi.fn()} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  const trigger=screen.getByRole("button",{name:"创建 CSV 导出"});
  await userEvent.click(trigger);
  const dialog=screen.getByRole("dialog",{name:"确认历史导出"});
  const confirm=screen.getByRole("button",{name:"确认导出"});
  const cancel=screen.getByRole("button",{name:"取消"});
  expect(dialog).toHaveFocus();
  await userEvent.tab();
  expect(confirm).toHaveFocus();
  await userEvent.tab({shift:true});
  expect(cancel).toHaveFocus();
  await userEvent.tab();
  expect(confirm).toHaveFocus();
  await userEvent.click(confirm);
  await waitFor(()=>expect(screen.getByLabelText("导出开始时间（UTC）")).toHaveFocus());
});

it("does not create export for an invalid inverted range",async()=>{
  const create=vi.fn();
  render(<ExportPanel range={range} artifact={null} failure={null} onCreate={create} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  const start=screen.getByLabelText("导出开始时间（UTC）"),end=screen.getByLabelText("导出结束时间（UTC）");
  await userEvent.clear(start);
  await userEvent.type(start,"2026-08-11T00:00:00.000");
  await userEvent.clear(end);
  await userEvent.type(end,"2026-08-10T00:00:00.000");
  await userEvent.click(screen.getByRole("button",{name:"创建 JSONL 导出"}));
  await userEvent.click(screen.getByRole("button",{name:"确认导出"}));
  expect(create).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("结束时间晚于开始时间");
  expect(screen.getByRole("alert")).not.toHaveTextContent("1970 年");
});

it("refreshes and downloads a verified artifact",async()=>{
  const refresh=vi.fn(),download=vi.fn();
  render(<ExportPanel range={range} artifact={artifact} failure={null} onCreate={vi.fn()} onRefresh={refresh} onDownload={download}/>);
  await userEvent.click(screen.getByRole("button",{name:"刷新导出状态"}));
  expect(refresh).toHaveBeenCalledWith("e1");
  await userEvent.click(screen.getByRole("button",{name:"下载已验证的 CSV"}));
  expect(download).toHaveBeenCalledWith("e1");
});

it("renders jsonl artifact download label",()=>{
  render(<ExportPanel range={range} artifact={{...artifact,format:"jsonl"}} failure={null} onCreate={vi.fn()} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  expect(screen.getByRole("button",{name:"下载已验证的 JSONL"})).toBeTruthy();
});

it("renders public failure alert without leaking paths or AI controls",()=>{
  render(<ExportPanel range={range} artifact={null} failure={{ok:false,code:"MONITOR_EXPORT_FAILED",message:"history export failed"}} onCreate={vi.fn()} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("MONITOR_EXPORT_FAILED");
  expect(screen.queryByLabelText(/file name/i)).toBeNull();
  expect(screen.queryByText(/AI snapshot|diagnostic session/i)).toBeNull();
});

it("syncs clean query bounds, retains an edited draft, and restores the query on request",async()=>{
  const first={startNs:1786320000000000000n,endNs:1786320002000000000n};
  const second={startNs:1786320010000000000n,endNs:1786320012000000000n};
  const callbacks={artifact:null,failure:null,onCreate:vi.fn(),onRefresh:vi.fn(),onDownload:vi.fn()};
  const {rerender}=render(<ExportPanel range={first} {...callbacks}/>);
  const start=screen.getByLabelText("导出开始时间（UTC）") as HTMLInputElement;
  rerender(<ExportPanel range={second} {...callbacks}/>);
  await waitFor(()=>expect(start.value).toBe("2026-08-10T00:00:10.000"));
  fireEvent.input(start,{target:{value:"2026-08-10T00:00:11.000"}});
  rerender(<ExportPanel range={first} {...callbacks}/>);
  expect(start.value).toBe("2026-08-10T00:00:11.000");
  expect(screen.getByText("查询范围已更新，保留当前导出范围。")).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"使用查询范围"}));
  expect(start.value).toBe("2026-08-10T00:00");
});

it("shows reducer-owned submitted range only for its artifact ID",async()=>{
  const first={startNs:1786320000000000000n,endNs:1786320002000000000n};
  const second={startNs:1786320010000000000n,endNs:1786320012000000000n};
  const create=vi.fn();
  const callbacks={failure:null,onCreate:create,onRefresh:vi.fn(),onDownload:vi.fn()};
  const {rerender}=render(<ExportPanel range={first} artifact={artifact}
    submitted={{...first,exportId:"e1",format:"csv"}} {...callbacks}/>);
  expect(screen.getByText(/提交时范围.*00:00:00.*00:00:02/)).toBeTruthy();
  rerender(<ExportPanel range={second} artifact={artifact}
    submitted={{...first,exportId:"e1",format:"csv"}} {...callbacks}/>);
  expect(screen.getByText(/提交时范围.*00:00:00.*00:00:02/)).toBeTruthy();
  rerender(<ExportPanel range={second} artifact={{...artifact,exportId:"e2",format:"jsonl"}}
    submitted={{...first,exportId:"e1",format:"csv"}} {...callbacks}/>);
  expect(screen.queryByText(/提交时范围/)).toBeNull();
  rerender(<ExportPanel range={second} artifact={{...artifact,exportId:"e2",format:"jsonl"}}
    submitted={{...second,exportId:"e2",format:"jsonl"}} {...callbacks}/>);
  expect(screen.getByText(/提交时范围.*00:00:10.*00:00:12/)).toBeTruthy();
});

it("uses reducer pending props to serialize create, refresh and download",async()=>{
  const create=vi.fn(),refresh=vi.fn(),download=vi.fn();
  const callbacks={range,artifact,failure:null,onCreate:create,onRefresh:refresh,onDownload:download};
  const {rerender}=render(<ExportPanel {...callbacks} refreshing/>);
  expect(screen.getByRole("button",{name:"创建 CSV 导出"})).toBeDisabled();
  expect(screen.getByRole("button",{name:"刷新导出状态"})).toBeDisabled();
  rerender(<ExportPanel {...callbacks} creating/>);
  expect(screen.getByRole("button",{name:"创建 JSONL 导出"})).toBeDisabled();
  rerender(<ExportPanel {...callbacks} downloading/>);
  expect(screen.getByRole("button",{name:"下载已验证的 CSV"})).toBeDisabled();
  rerender(<ExportPanel {...callbacks}/>);
  expect(screen.getByRole("button",{name:"创建 CSV 导出"})).toBeEnabled();
  await userEvent.click(screen.getByRole("button",{name:"刷新导出状态"}));
  expect(refresh).toHaveBeenCalledWith("e1");
});
