import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {fireEvent,render,screen,waitFor} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {GroupPanel} from "../src/components/GroupPanel";
import {watchGroup} from "./fixtures";

class ControlledFileReader{
  static requests:ControlledFileReader[]=[];
  result:string|null=null;
  onload:(()=>void)|null=null;
  onerror:(()=>void)|null=null;
  readAsText(file:Blob):void{void file;ControlledFileReader.requests.push(this);}
  succeed(text:string):void{this.result=text;this.onload?.();}
  fail():void{this.onerror?.();}
}

const empty='{"schemaVersion":1,"groups":[]}';
const one='{"schemaVersion":1,"groups":[{"name":"New","description":"","intervalMs":250,"items":[]}]}';
const props=(onImport=vi.fn())=>({
  groups:[watchGroup()],selectedGroupId:"group",
  draft:{sourceGroupId:"group",expectedRevision:1n,name:"Group",description:"",intervalMs:250,items:[{kind:"variable" as const,expression:"counter"}]},
  failure:null,onSelect:vi.fn(),onDraftChange:vi.fn(),onRemove:vi.fn(),onNew:vi.fn(),onSave:vi.fn(),onDelete:vi.fn(),
  onImport,onExport:vi.fn(),
});

beforeEach(()=>{ControlledFileReader.requests=[];vi.stubGlobal("FileReader",ControlledFileReader);});
afterEach(()=>vi.unstubAllGlobals());

function select(name:string):void{
  fireEvent.change(screen.getByTestId("group-import-file"),{target:{files:[new File([name],name,{type:"application/json"})]}});
}

it("withdraws a previous confirmation immediately and reports a later read failure",async()=>{
  const onImport=vi.fn();
  render(<GroupPanel {...props(onImport)}/>);
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  select("first.json");
  ControlledFileReader.requests[0]!.succeed(empty);
  expect(await screen.findByText(/将导入 0 个观测组/)).toBeTruthy();
  expect(screen.getByRole("button",{name:"确认导入"})).toBeEnabled();

  select("second.json");
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  expect(screen.getByRole("status")).toHaveTextContent("正在读取导入文件");
  ControlledFileReader.requests[1]!.fail();
  expect(await screen.findByRole("alert")).toHaveTextContent("无法读取导入文件");
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  expect(onImport).not.toHaveBeenCalled();
});

it("allows only the last selection to supply the confirmed document after out-of-order success",async()=>{
  const onImport=vi.fn();
  render(<GroupPanel {...props(onImport)}/>);
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  select("old.json");
  select("new.json");
  ControlledFileReader.requests[1]!.succeed(one);
  expect(await screen.findByText(/将导入 1 个观测组/)).toBeTruthy();
  ControlledFileReader.requests[0]!.succeed(empty);
  await Promise.resolve();
  await waitFor(()=>expect(screen.getByText(/将导入 1 个观测组/)).toBeTruthy());
  await userEvent.click(screen.getByRole("button",{name:"确认导入"}));
  expect(onImport).toHaveBeenCalledExactlyOnceWith({schemaVersion:1,groups:[{name:"New",description:"",intervalMs:250,items:[]}]});
});

it("ignores an older failure after a newer valid preview",async()=>{
  const onImport=vi.fn();
  render(<GroupPanel {...props(onImport)}/>);
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  select("old.json");
  select("new.json");
  ControlledFileReader.requests[1]!.succeed(one);
  expect(await screen.findByText(/将导入 1 个观测组/)).toBeTruthy();
  ControlledFileReader.requests[0]!.fail();
  await Promise.resolve();
  expect(screen.queryByRole("alert")).toBeNull();
  await userEvent.click(screen.getByRole("button",{name:"确认导入"}));
  expect(onImport).toHaveBeenCalledExactlyOnceWith({schemaVersion:1,groups:[{name:"New",description:"",intervalMs:250,items:[]}]});
});

it("invalidates pending reads when closed or cancelled and does not revive a discarded preview",async()=>{
  const onImport=vi.fn();
  render(<GroupPanel {...props(onImport)}/>);
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  select("closed.json");
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  ControlledFileReader.requests[0]!.succeed(one);
  await Promise.resolve();
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  select("cancelled.json");
  fireEvent.click(screen.getByRole("button",{name:"取消"}));
  ControlledFileReader.requests[1]!.succeed(one);
  await Promise.resolve();
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  expect(onImport).not.toHaveBeenCalled();
});

it.each([
  {kind:"JSON",content:"not-json",error:"导入文件不是有效的 JSON"},
  {kind:"schema",content:'{"schemaVersion":1,"groups":{}}',error:"导入文件无效"},
])("replaces an older preview with a $kind error and never submits it",async({content,error})=>{
  const onImport=vi.fn();
  render(<GroupPanel {...props(onImport)}/>);
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  select("valid.json");
  ControlledFileReader.requests[0]!.succeed(one);
  expect(await screen.findByText(/将导入 1 个观测组/)).toBeTruthy();
  select("invalid.json");
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  ControlledFileReader.requests[1]!.succeed(content);
  expect(await screen.findByRole("alert")).toHaveTextContent(error);
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  expect(onImport).not.toHaveBeenCalled();
});

it("ignores a read completion after unmount",async()=>{
  const onImport=vi.fn();
  const view=render(<GroupPanel {...props(onImport)}/>);
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  select("unmounted.json");
  view.unmount();
  render(<GroupPanel {...props(onImport)}/>);
  ControlledFileReader.requests[0]!.succeed(one);
  await Promise.resolve();
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  expect(onImport).not.toHaveBeenCalled();
});

it("can reselect the same file while the older read is pending and only submits the newest result",async()=>{
  const onImport=vi.fn();
  render(<GroupPanel {...props(onImport)}/>);
  await userEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  const input=screen.getByTestId("group-import-file") as HTMLInputElement;
  const same=new File([empty],"same.json",{type:"application/json"});
  await userEvent.upload(input,same);
  await userEvent.upload(input,same);
  expect(ControlledFileReader.requests).toHaveLength(2);
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  ControlledFileReader.requests[0]!.succeed(empty);
  await Promise.resolve();
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  ControlledFileReader.requests[1]!.succeed(one);
  expect(await screen.findByText(/将导入 1 个观测组/)).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"确认导入"}));
  expect(onImport).toHaveBeenCalledExactlyOnceWith({schemaVersion:1,groups:[{name:"New",description:"",intervalMs:250,items:[]}]});
});
