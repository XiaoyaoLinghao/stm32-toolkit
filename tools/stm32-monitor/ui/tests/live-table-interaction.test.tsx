import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {LiveTable} from "../src/components/LiveTable";

it("labels each curve button with its next action while reducer selection remains authoritative",async()=>{
  const toggle=vi.fn();
  const row={watch:{kind:"variable" as const,expression:"counter"},displayValue:"42",rawHex:null,
    typeName:"int",capturedAtUtc:"",trend:"up" as const,errorCode:null,numericValue:42};
  const view=render(<LiveTable rows={[row]} selectedSeries={[]} onSeriesToggle={toggle}/>);
  const show=screen.getByRole("button",{name:"显示曲线"});
  expect(show).toHaveAttribute("aria-pressed","false");
  await userEvent.click(show);
  expect(toggle).toHaveBeenCalledExactlyOnceWith("variable:counter");

  view.rerender(<LiveTable rows={[row]} selectedSeries={["variable:counter"]} onSeriesToggle={toggle}/>);
  const hide=screen.getByRole("button",{name:"隐藏曲线"});
  expect(hide).toHaveAttribute("aria-pressed","true");
  await userEvent.click(hide);
  expect(toggle).toHaveBeenCalledTimes(2);
  expect(toggle).toHaveBeenLastCalledWith("variable:counter");

  view.rerender(<LiveTable rows={[row]} selectedSeries={[]} onSeriesToggle={toggle}/>);
  expect(screen.getByRole("button",{name:"显示曲线"})).toHaveAttribute("aria-pressed","false");
});

it("explains the eight-curve cap, still allows hiding, and enables the next curve after removal",async()=>{
  const toggle=vi.fn();
  const rows=Array.from({length:9},(_,index)=>({watch:{kind:"variable" as const,expression:`point${index}`},
    displayValue:String(index),rawHex:null,typeName:"int",capturedAtUtc:"",trend:"none" as const,
    errorCode:null,numericValue:index}));
  const selected=rows.slice(0,8).map(row=>`variable:${row.watch.expression}`);
  const view=render(<LiveTable rows={rows} selectedSeries={selected} onSeriesToggle={toggle}/>);
  expect(screen.getByText("已选择 8 / 8 条曲线")).toBeTruthy();
  expect(screen.getByText("最多只能选择 8 条曲线；先移除已选曲线。")).toBeTruthy();
  expect(screen.getByRole("button",{name:"显示曲线"})).toBeDisabled();
  await userEvent.click(screen.getAllByRole("button",{name:"隐藏曲线"})[0]!);
  expect(toggle).toHaveBeenCalledWith("variable:point0");
  view.rerender(<LiveTable rows={rows} selectedSeries={selected.slice(1)} onSeriesToggle={toggle}/>);
  expect(screen.getAllByRole("button",{name:"显示曲线"})).toHaveLength(2);
  for(const button of screen.getAllByRole("button",{name:"显示曲线"}))expect(button).toBeEnabled();
});

it("keeps an already-selected curve removable after its row leaves the current group",async()=>{
  const toggle=vi.fn();
  render(<LiveTable rows={[]} selectedSeries={["variable:orphan"]} onSeriesToggle={toggle}/>);
  expect(screen.getByText("已选择 1 / 8 条曲线")).toBeTruthy();
  expect(screen.getByText("变量 orphan")).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:/移除曲线.*orphan/}));
  expect(toggle).toHaveBeenCalledExactlyOnceWith("variable:orphan");
});

it("labels only empty no-run preview cells while preserving errors and sampled values",()=>{
  const watch={kind:"variable" as const,expression:"counter"};
  const empty={watch,displayValue:"",rawHex:null,typeName:null,capturedAtUtc:"",trend:"none" as const,errorCode:null,numericValue:null};
  const sampled={...empty,watch:{kind:"variable" as const,expression:"sampled"},displayValue:"42",capturedAtUtc:"2026-10-21T00:00:00Z"};
  const error={...empty,watch:{kind:"variable" as const,expression:"bad"},errorCode:"READ_FAILED"};
  const view=render(<LiveTable rows={[empty,sampled,error]} selectedSeries={[]} waiting="connection" fresh={false} onSeriesToggle={vi.fn()}/>);
  expect(screen.getByRole("region",{name:"最新数值"})).toHaveTextContent("等待连接");
  expect(screen.getByText("42")).toBeVisible();
  expect(screen.getByText("READ_FAILED")).toBeTruthy();
  expect(screen.queryByText("非最新数据")).toBeNull();
  view.rerender(<LiveTable rows={[empty]} selectedSeries={[]} waiting="start" onSeriesToggle={vi.fn()}/>);
  expect(screen.getByText("等待开始")).toBeVisible();
  view.rerender(<LiveTable rows={[empty]} selectedSeries={[]} fresh={false} onSeriesToggle={vi.fn()}/>);
  expect(screen.queryByText("等待开始")).toBeNull();
});
