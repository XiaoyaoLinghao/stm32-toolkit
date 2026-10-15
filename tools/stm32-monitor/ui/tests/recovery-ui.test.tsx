import {expect,it,vi} from "vitest";
import {fireEvent,render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {OperationRegion} from "../src/components/OperationRegion";
import {CatalogPanel} from "../src/components/CatalogPanel";
import type {MonitorState} from "../src/state/model";

const failure=(requestId:bigint,code:string,recovery:"read-retry"|"write-confirm"|"reconcile",summary:string)=>({
  ok:false as const,requestId,code,message:"raw diagnostic",recovery,summary,
});
it("shows every operation failure and dismisses only its exact record",async()=>{
  const retry=vi.fn(),dismiss=vi.fn();
  render(<OperationRegion failures={{history:failure(1n,"HISTORY_DOWN","read-retry","历史查询 · c2"),
    "groups.create":failure(2n,"GROUP_DOWN","write-confirm","创建观测组 · Motor")}}
    pending={{}} onRetry={retry} onDismiss={dismiss}/>);
  expect(screen.getByText("历史查询 · c2")).toBeTruthy();
  expect(screen.getByText("创建观测组 · Motor")).toBeTruthy();
  const alerts=screen.getAllByRole("alert");
  expect(alerts).toHaveLength(2);
  fireEvent.click(alerts[0]!.querySelector("button:last-of-type")!);
  expect(dismiss).toHaveBeenCalledWith("history",1n);
  expect(retry).not.toHaveBeenCalled();
});
it("requires an explicit confirmation and rejects a stale same-batch handler",async()=>{
  const retry=vi.fn();
  render(<OperationRegion failures={{"groups.create":failure(9n,"REJECTED","write-confirm","创建观测组 · original")}}
    pending={{}} onRetry={retry} onDismiss={vi.fn()}/>);
  await userEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
  expect(screen.getByRole("dialog",{name:"确认重试上次写入"})).toHaveTextContent("original");
  const stale=screen.getByRole("button",{name:"确认重试上次写入"});
  fireEvent.click(screen.getByRole("button",{name:"取消"}));
  fireEvent.click(stale);
  expect(retry).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
  await userEvent.click(screen.getByRole("button",{name:"确认重试上次写入"}));
  expect(retry).toHaveBeenCalledWith("groups.create",9n);
});
it("keeps initialization recoverable and disables an in-flight reconcile",()=>{
  const failures:MonitorState["failures"]={initial:failure(1n,"BOOT_DOWN","read-retry","初始化读取"),
    "groups.import":failure(2n,"MONITOR_TRANSPORT_FAILED","reconcile","导入观测组 · 2 组")};
  render(<OperationRegion failures={failures} pending={{}} reconciling={{"groups.import":2n}}
    allowDismissInitial={false} onRetry={vi.fn()} onDismiss={vi.fn()}/>);
  const alerts=screen.getAllByRole("alert");
  expect(alerts[0]!.querySelector("button:last-of-type")).toHaveTextContent("重试初始化");
  expect(alerts[1]!.querySelector("button:first-of-type")).toBeDisabled();
});
it("keeps the last successful catalog rows visible when a new query fails",async()=>{
  const search=vi.fn();
  const descriptor={selector:"counter",typeName:"int",kind:"int",byteSize:4,signed:true,
    encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]};
  render(<CatalogPanel connected bindingEpoch={3n}
    variables={{kind:"variables",query:"old",bindingKey:"w/s/p/3",cursor:null,items:[descriptor],nextCursor:"c2"}}
    registers={null} onSearch={search} onNext={vi.fn()} onAdd={vi.fn()}/>);
  expect(screen.getByText("counter")).toBeTruthy();
  fireEvent.input(screen.getByPlaceholderText("输入符号或寄存器前缀"),{target:{value:"new"}});
  expect(search).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  expect(search).toHaveBeenCalledWith("variables","new");
  expect(screen.getByText("counter")).toBeTruthy();
  expect(screen.getByText("显示上次成功的查询结果；当前搜索尚未成功。")).toBeTruthy();
  expect(screen.getByRole("button",{name:"加入观测组草稿"})).toBeDisabled();
  expect(screen.getByRole("button",{name:"下一页"})).toBeDisabled();
});
