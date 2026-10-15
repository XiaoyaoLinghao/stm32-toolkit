import {expect,it,vi} from "vitest";
import {fireEvent,render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {GroupPanel} from "../src/components/GroupPanel";
import {CatalogPanel} from "../src/components/CatalogPanel";
import {SamplingControls} from "../src/components/SamplingControls";
import {OperationRegion} from "../src/components/OperationRegion";
import {statusResult,watchGroup} from "./fixtures";
import type {RegisterDescriptor} from "../src/api/contract";

const first=watchGroup();
const second={...first,groupId:"other",name:"Other"};
const panel=(overrides:Record<string,unknown>={})=>({
  groups:[first,second],selectedGroupId:first.groupId,
  draft:{sourceGroupId:first.groupId,expectedRevision:first.revision,name:"Unsent",description:"",intervalMs:250,items:first.items},
  dirty:true,navigation:null,sourceProblem:null,editorGeneration:5n,
  failure:null,onSelect:vi.fn(),onDraftChange:vi.fn(),onRemove:vi.fn(),onNew:vi.fn(),
  onSave:vi.fn(),onDelete:vi.fn(),onImport:vi.fn(),onExport:vi.fn(),
  onNavigateConfirm:vi.fn(),onNavigateCancel:vi.fn(),onSaveAsNew:vi.fn(),onRefresh:vi.fn(),
  ...overrides,
});

it("shows a controlled dirty-navigation choice and freezes editor inputs until resolved",async()=>{
  const confirm=vi.fn(),cancel=vi.fn();
  render(<GroupPanel {...panel({navigation:{kind:"group",groupId:"other"},
    onNavigateConfirm:confirm,onNavigateCancel:cancel})}/>);
  expect(screen.getByRole("dialog",{name:"未保存的观测组修改"})).toBeTruthy();
  expect(screen.getByLabelText("名称")).toBeDisabled();
  await userEvent.click(screen.getByRole("button",{name:"继续编辑"}));
  expect(cancel).toHaveBeenCalledOnce();
  await userEvent.click(screen.getByRole("button",{name:"放弃修改并继续"}));
  expect(confirm).toHaveBeenCalledOnce();
});

it("withdraws a stale delete confirmation when revision or editor generation changes",async()=>{
  const onDelete=vi.fn();
  const view=render(<GroupPanel {...panel({onDelete})}/>);
  await userEvent.click(screen.getByRole("button",{name:"删除"}));
  expect(screen.getByRole("button",{name:"确认删除"})).toBeEnabled();
  view.rerender(<GroupPanel {...panel({onDelete,groups:[{...first,revision:2n},second]})}/>);
  expect(screen.queryByRole("button",{name:"确认删除"})).toBeNull();
  expect(onDelete).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"删除"}));
  view.rerender(<GroupPanel {...panel({onDelete,groups:[{...first,revision:2n},second],editorGeneration:6n})}/>);
  expect(screen.queryByRole("button",{name:"确认删除"})).toBeNull();
});

it("invalidates delete synchronously when navigation is requested before a render",async()=>{
  const onDelete=vi.fn(),onSelect=vi.fn();
  render(<GroupPanel {...panel({onDelete,onSelect})}/>);
  await userEvent.click(screen.getByRole("button",{name:"删除"}));
  const staleConfirm=screen.getByRole("button",{name:"确认删除"});
  fireEvent.click(screen.getByRole("button",{name:"Other (1)"}));
  fireEvent.click(staleConfirm);
  expect(onSelect).toHaveBeenCalledWith("other");
  expect(onDelete).not.toHaveBeenCalled();
});

it("loads an empty catalog query explicitly and rejects non-sampleable registers",async()=>{
  const search=vi.fn(),add=vi.fn();
  const register:RegisterDescriptor={selector:"GPIO.ODR",sizeBits:32,access:"wo",readAction:"none",
    resetValue:null,resetMask:null,fields:[],sampleable:false,requiresAccessAcknowledgement:false};
  render(<CatalogPanel connected bindingEpoch={1n} variables={null}
    registers={{kind:"registers",query:"",bindingKey:"w/s/p/1",cursor:null,items:[register],nextCursor:null}}
    onSearch={search} onNext={vi.fn()} onAdd={add}/>);
  await userEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  expect(search).toHaveBeenCalledWith("variables","");
  await userEvent.click(screen.getByRole("tab",{name:"寄存器"}));
  await userEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  expect(search).toHaveBeenCalledWith("registers","");
  expect(screen.getByRole("button",{name:"加入观测组草稿"})).toBeDisabled();
  expect(screen.getByText(/wo.*none/)).toBeTruthy();
  expect(add).not.toHaveBeenCalled();
});

it("does not add an older catalog query while a new query is being composed",async()=>{
  const add=vi.fn();
  const register:RegisterDescriptor={selector:"GPIO.IDR",sizeBits:32,access:"ro",readAction:"safe",
    resetValue:null,resetMask:null,fields:[],sampleable:true,requiresAccessAcknowledgement:false};
  render(<CatalogPanel connected bindingEpoch={1n} variables={null}
    registers={{kind:"registers",query:"GPIO",bindingKey:"w/s/p/1",cursor:null,items:[register],nextCursor:null}}
    onSearch={vi.fn()} onNext={vi.fn()} onAdd={add}/>);
  await userEvent.click(screen.getByRole("tab",{name:"寄存器"}));
  await userEvent.type(screen.getByRole("textbox",{name:"搜索"}),"USART");
  expect(screen.getByText(/显示上次成功的查询结果/)).toBeTruthy();
  expect(screen.getByRole("button",{name:"加入观测组草稿"})).toBeDisabled();
  expect(add).not.toHaveBeenCalled();
});

it("distinguishes the next saved sampling target from the active run group",()=>{
  const status=statusResult().sampling;
  render(<SamplingControls status={{...status,state:"RUNNING",active:true,groupId:"active",groupRevision:1n,runId:"run"}}
    group={null} activeGroupName="Running group" onStart={vi.fn()} onPause={vi.fn()}
    onResume={vi.fn()} onStop={vi.fn()} failure={null}/>);
  expect(screen.getByText(/下次开始采样.*尚未选择/)).toBeTruthy();
  expect(screen.getByText(/当前运行.*Running group/)).toBeTruthy();
  expect(screen.getByRole("button",{name:"暂停采样"})).toBeEnabled();
  expect(screen.getByRole("button",{name:"停止采样"})).toBeEnabled();
});

it("previews imported group names and counts with the no-overwrite warning",async()=>{
  render(<GroupPanel {...panel()}/>);
  await userEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  await userEvent.upload(screen.getByTestId("group-import-file"),new File([
    JSON.stringify({schemaVersion:1,groups:[{name:"Alpha",description:"",intervalMs:250,
      items:[{kind:"variable",expression:"a"},{kind:"register",registerPath:"GPIO.IDR"}]}]}),
  ],"groups.json",{type:"application/json"}));
  expect(await screen.findByText(/Alpha · 2 个对象/)).toBeTruthy();
  expect(screen.getByText(/不会覆盖已有组.*名称冲突由服务端检查/)).toBeTruthy();
});

it("offers GET-only group refresh for a conflict without a write confirmation dialog",async()=>{
  const onRetry=vi.fn();
  render(<OperationRegion failures={{"groups.update":{ok:false,code:"MONITOR_GROUP_CONFLICT",
    message:"name collision",requestId:4n,recovery:"groups-refresh",summary:"保存观测组"}}}
    pending={{}} onRetry={onRetry} onDismiss={vi.fn()}/>);
  expect(screen.getByText(/刷新观测组列表以核对版本和名称/)).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"刷新观测组"}));
  expect(onRetry).toHaveBeenCalledWith("groups.update",4n);
  expect(screen.queryByRole("dialog",{name:"确认重试上次写入"})).toBeNull();
});
