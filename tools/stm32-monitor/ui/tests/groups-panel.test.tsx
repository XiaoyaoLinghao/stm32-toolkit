import {expect,it,vi} from "vitest";
import {fireEvent,render,screen,waitFor} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {GroupPanel} from "../src/components/GroupPanel";
import {watchGroup} from "./fixtures";

const group=watchGroup();
function props(overrides:Record<string,unknown>={}){
  return{
    groups:[group],
    selectedGroupId:"group",
    draft:{sourceGroupId:"group",expectedRevision:1n,name:"Group",description:"",intervalMs:250,items:[{kind:"variable" as const,expression:"counter"}]},
    failure:null,
    onSelect:vi.fn(),
    onDraftChange:vi.fn(),
    onRemove:vi.fn(),
    onNew:vi.fn(),
    onSave:vi.fn(),
    onDelete:vi.fn(),
    onImport:vi.fn(),
    onExport:vi.fn(),
    ...overrides,
  };
}

it("lists groups and selects one",async()=>{
  const select=vi.fn();
  render(<GroupPanel {...props({onSelect:select})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Group (1)"}));
  expect(select).toHaveBeenCalledWith("group");
});

it("new group creates and saves",async()=>{
  const create=vi.fn(),save=vi.fn();
  render(<GroupPanel {...props({
    selectedGroupId:null,
    draft:{sourceGroupId:null,expectedRevision:null,name:"",description:"",intervalMs:250,items:[]},
    onNew:create,onSave:save,
  })}/>);
  expect(screen.getByRole("button",{name:"创建观测组"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"新建观测组"}));
  expect(create).toHaveBeenCalled();
});

it("ignores a non-finite interval input",async()=>{
  const change=vi.fn();
  render(<GroupPanel {...props({onDraftChange:change})}/>);
  const interval=screen.getByLabelText("采样间隔（ms）");
  await userEvent.clear(interval);
  await userEvent.type(interval,"abc");
  expect(change).toHaveBeenCalled();
});

it("edits draft name, description and interval",async()=>{
  const change=vi.fn();
  render(<GroupPanel {...props({onDraftChange:change})}/>);
  const nameInput=screen.getByLabelText("名称");
  await userEvent.clear(nameInput);
  await userEvent.type(nameInput,"Renamed");
  expect(change).toHaveBeenCalled();
  const description=screen.getByLabelText("描述");
  await userEvent.clear(description);
  await userEvent.type(description,"a motor controller");
  expect(change).toHaveBeenCalled();
  const interval=screen.getByLabelText("采样间隔（ms）");
  await userEvent.clear(interval);
  await userEvent.type(interval,"500");
  expect(change).toHaveBeenCalled();
});

it("removes a register watch from the draft",async()=>{
  const remove=vi.fn();
  render(<GroupPanel {...props({draft:{sourceGroupId:"group",expectedRevision:1n,name:"Group",description:"",intervalMs:250,items:[{kind:"register" as const,registerPath:"TIM2_CNT"}]},onRemove:remove})}/>);
  await userEvent.click(screen.getByRole("button",{name:"移除"}));
  expect(remove).toHaveBeenCalledWith("register:TIM2_CNT");
});

it("saves the selected group",async()=>{
  const save=vi.fn();
  render(<GroupPanel {...props({onSave:save})}/>);
  await userEvent.click(screen.getByRole("button",{name:"保存观测组"}));
  expect(save).toHaveBeenCalled();
});

it("deletes only after explicit confirmation",async()=>{
  const del=vi.fn();
  render(<GroupPanel {...props({onDelete:del})}/>);
  await userEvent.click(screen.getByRole("button",{name:"删除"}));
  expect(del).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"确认删除"}));
  expect(del).toHaveBeenCalledWith("group",1n,0n);
});

it("cancelling delete does not call delete",async()=>{
  const del=vi.fn();
  render(<GroupPanel {...props({onDelete:del})}/>);
  await userEvent.click(screen.getByRole("button",{name:"删除"}));
  await userEvent.click(screen.getByRole("button",{name:"取消"}));
  expect(del).not.toHaveBeenCalled();
});

it("renders failure alert",()=>{
  render(<GroupPanel {...props({failure:{ok:false,code:"GROUPS_FAILED",message:"cannot save"}})}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("GROUPS_FAILED");
});

it("imports a group document after preview and confirmation",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  const file=screen.getByTestId("group-import-file") as HTMLInputElement;
  await userEvent.upload(file,new File(['{"schemaVersion":1,"groups":[]}'],"groups.json",{type:"application/json"}));
  const confirm=await screen.findByRole("button",{name:"确认导入"});
  await waitFor(()=>expect(file.value).toBe(""));
  expect(importFn).not.toHaveBeenCalled();
  await userEvent.click(confirm);
  expect(importFn).toHaveBeenCalledWith({schemaVersion:1,groups:[]});
});

it("finishes reading after the group panel unmounts without touching its detached file input",async()=>{
  const importFn=vi.fn();
  const readAsText=FileReader.prototype.readAsText;
  let resolveRead!:()=>void;
  const readCompleted=new Promise<void>(resolve=>{resolveRead=resolve;});
  const readSpy=vi.spyOn(FileReader.prototype,"readAsText").mockImplementation(function(this:FileReader,blob:Blob,encoding?:string){
    this.addEventListener("loadend",resolveRead,{once:true});
    readAsText.call(this,blob,encoding);
  });
  try{
    const view=render(<GroupPanel {...props({onImport:importFn})}/>);
    fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
    const input=screen.getByTestId("group-import-file") as HTMLInputElement;
    const file=new File(['{"schemaVersion":1,"groups":[]}'],"groups.json",{type:"application/json"});
    fireEvent.change(input,{target:{files:[file]}});
    expect(readSpy).toHaveBeenCalledTimes(1);
    const beforeUnmount={value:input.value,fileCount:input.files?.length};
    expect(beforeUnmount.value).toBe("");
    view.unmount();
    expect(input.isConnected).toBe(false);
    const lateValueWrite=vi.spyOn(input,"value","set");
    try{
      await readCompleted;
      expect(lateValueWrite).not.toHaveBeenCalled();
      expect({value:input.value,fileCount:input.files?.length}).toEqual(beforeUnmount);
      expect(importFn).not.toHaveBeenCalled();
      expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
      expect(screen.queryByRole("region",{name:"观测组"})).toBeNull();
    }finally{
      lateValueWrite.mockRestore();
    }
  }finally{
    readSpy.mockRestore();
  }
});

it("rejects invalid import JSON with an error and no confirmation",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(["not-json"],"bad.json",{type:"application/json"}));
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  expect(importFn).not.toHaveBeenCalled();
});

it("cancels an import preview without sending",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(['{"schemaVersion":1,"groups":[]}'],"groups.json",{type:"application/json"}));
  const cancel=await screen.findByRole("button",{name:"取消"});
  await userEvent.click(cancel);
  expect(importFn).not.toHaveBeenCalled();
});

it("ignores an import change event without a file",()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  fireEvent.change(screen.getByTestId("group-import-file"),{target:{files:[]}});
  expect(importFn).not.toHaveBeenCalled();
});

it("shows empty draft for a new group selection",()=>{
  render(<GroupPanel {...props({groups:[],selectedGroupId:null,
    draft:{sourceGroupId:null,expectedRevision:null,name:"",description:"",intervalMs:250,items:[]}})}/>);
  expect(screen.queryByRole("button",{name:"Group (1)"})).toBeNull();
  expect(screen.getByRole("button",{name:"新建观测组"})).toBeTruthy();
});

it("exports authoritative groups as a blob download on click",async()=>{
  const created:URL[]=[];
  const originalCreate=URL.createObjectURL;
  const originalRevoke=URL.revokeObjectURL;
  URL.createObjectURL=vi.fn(()=>{const url=new URL("blob:test-export");created.push(url);return url.href;}) as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL=vi.fn() as unknown as typeof URL.revokeObjectURL;
  try{
    render(<GroupPanel {...props({groups:[watchGroup()]})}/>);
    await userEvent.click(screen.getByRole("button",{name:"导出观测组 JSON"}));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(created[0]!.href);
  }finally{
    URL.createObjectURL=originalCreate;
    URL.revokeObjectURL=originalRevoke;
  }
});

it("surfaces an invalid schema before confirmation and hides the preview",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(['{"schemaVersion":1,"groups":{}}'],"bad-schema.json",{type:"application/json"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("导入文件无效");
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  expect(importFn).not.toHaveBeenCalled();
});

it("closes the import preview when toggling the import button again",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(['{"schemaVersion":1,"groups":[]}'],"groups.json",{type:"application/json"}));
  expect(await screen.findByRole("button",{name:"确认导入"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
  expect(importFn).not.toHaveBeenCalled();
});

it("lets an editor choose a different adjacent pair without changing existing watches",async()=>{
  const change=vi.fn();
  const items=[{kind:"variable" as const,expression:"bytes[0]"},{kind:"variable" as const,expression:"bytes[1]"},
    {kind:"variable" as const,expression:"bytes[2]"}];
  const draft={sourceGroupId:"group",expectedRevision:1n,name:"Group",description:"",intervalMs:250,items};
  render(<GroupPanel {...props({draft,onDraftChange:change})}/>);
  await userEvent.click(screen.getByRole("button",{name:"合并16位"}));
  await userEvent.selectOptions(screen.getByLabelText("低字节"),"bytes[1]");
  await userEvent.selectOptions(screen.getByLabelText("高字节"),"bytes[2]");
  await userEvent.click(screen.getByRole("button",{name:"添加组合"}));
  expect(change).toHaveBeenCalledWith({...draft,items:[...items,
    {kind:"u16le",lowExpression:"bytes[1]",highExpression:"bytes[2]"}]});
});

it("invalidates a delete confirmation after the selected revision changes",async()=>{
  const del=vi.fn();
  const view=render(<GroupPanel {...props({onDelete:del,editorGeneration:1n})}/>);
  await userEvent.click(screen.getByRole("button",{name:"删除"}));
  expect(screen.getByRole("button",{name:"确认删除"})).toBeEnabled();
  view.rerender(<GroupPanel {...props({groups:[{...group,revision:2n}],onDelete:del,editorGeneration:1n})}/>);
  expect(screen.queryByRole("button",{name:"确认删除"})).toBeNull();
  expect(del).not.toHaveBeenCalled();
});

it("reports a local file read failure and leaves the import unsent",async()=>{
  const importFn=vi.fn();
  const read=vi.spyOn(FileReader.prototype,"readAsText").mockImplementation(function(this:FileReader){
    queueMicrotask(()=>this.dispatchEvent(new ProgressEvent("error")));
  });
  try{
    render(<GroupPanel {...props({onImport:importFn})}/>);
    await userEvent.click(screen.getByRole("button",{name:"导入观测组"}));
    await userEvent.upload(screen.getByTestId("group-import-file"),new File(["{}"],"groups.json",{type:"application/json"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("无法读取导入文件，请重新选择。");
    expect(screen.queryByRole("button",{name:"确认导入"})).toBeNull();
    expect(importFn).not.toHaveBeenCalled();
  }finally{read.mockRestore();}
});

it("keeps a conflicted draft available for reload or saving as a new group",async()=>{
  const reload=vi.fn(),saveAsNew=vi.fn(),reviewed=vi.fn(),save=vi.fn();
  render(<GroupPanel {...props({sourceProblem:"changed",onReload:reload,onSaveAsNew:saveAsNew,
    nameReviewRequired:true,onNameReviewed:reviewed,onSave:save})}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("原组版本已变化");
  expect(screen.getByRole("button",{name:"保存观测组"})).toBeDisabled();
  await userEvent.click(screen.getByRole("button",{name:"确认使用此名称"}));
  expect(reviewed).toHaveBeenCalledOnce();
  await userEvent.click(screen.getByRole("button",{name:"保留为新组"}));
  expect(saveAsNew).toHaveBeenCalledOnce();
  await userEvent.click(screen.getByRole("button",{name:"放弃草稿并载入最新版本"}));
  expect(reload).toHaveBeenCalledOnce();
  expect(save).not.toHaveBeenCalled();
});
