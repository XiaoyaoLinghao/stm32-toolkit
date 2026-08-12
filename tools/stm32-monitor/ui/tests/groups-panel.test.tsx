import {expect,it,vi} from "vitest";
import {fireEvent,render,screen} from "@testing-library/preact";
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
  expect(screen.getByRole("button",{name:"Create group"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"New group"}));
  expect(create).toHaveBeenCalled();
});

it("ignores a non-finite interval input",async()=>{
  const change=vi.fn();
  render(<GroupPanel {...props({onDraftChange:change})}/>);
  const interval=screen.getByLabelText("Interval ms");
  await userEvent.clear(interval);
  await userEvent.type(interval,"abc");
  expect(change).toHaveBeenCalled();
});

it("edits draft name, description and interval",async()=>{
  const change=vi.fn();
  render(<GroupPanel {...props({onDraftChange:change})}/>);
  const nameInput=screen.getByLabelText("Name");
  await userEvent.clear(nameInput);
  await userEvent.type(nameInput,"Renamed");
  expect(change).toHaveBeenCalled();
  const description=screen.getByLabelText("Description");
  await userEvent.clear(description);
  await userEvent.type(description,"a motor controller");
  expect(change).toHaveBeenCalled();
  const interval=screen.getByLabelText("Interval ms");
  await userEvent.clear(interval);
  await userEvent.type(interval,"500");
  expect(change).toHaveBeenCalled();
});

it("removes a register watch from the draft",async()=>{
  const remove=vi.fn();
  render(<GroupPanel {...props({draft:{sourceGroupId:"group",expectedRevision:1n,name:"Group",description:"",intervalMs:250,items:[{kind:"register" as const,registerPath:"TIM2_CNT"}]},onRemove:remove})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Remove"}));
  expect(remove).toHaveBeenCalledWith("register:TIM2_CNT");
});

it("saves the selected group",async()=>{
  const save=vi.fn();
  render(<GroupPanel {...props({onSave:save})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Save group"}));
  expect(save).toHaveBeenCalled();
});

it("deletes only after explicit confirmation",async()=>{
  const del=vi.fn();
  render(<GroupPanel {...props({onDelete:del})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Delete"}));
  expect(del).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Confirm delete"}));
  expect(del).toHaveBeenCalledWith("group");
});

it("cancelling delete does not call delete",async()=>{
  const del=vi.fn();
  render(<GroupPanel {...props({onDelete:del})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Delete"}));
  await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
  expect(del).not.toHaveBeenCalled();
});

it("renders failure alert",()=>{
  render(<GroupPanel {...props({failure:{ok:false,code:"GROUPS_FAILED",message:"cannot save"}})}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("GROUPS_FAILED");
});

it("imports a group document after preview and confirmation",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Import groups"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(['{"schemaVersion":1,"groups":[]}'],"groups.json",{type:"application/json"}));
  expect(importFn).not.toHaveBeenCalled();
  const confirm=await screen.findByRole("button",{name:"Confirm import"});
  await userEvent.click(confirm);
  expect(importFn).toHaveBeenCalledWith({schemaVersion:1,groups:[]});
});

it("rejects invalid import JSON with an error and no confirmation",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Import groups"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(["not-json"],"bad.json",{type:"application/json"}));
  expect(screen.queryByRole("button",{name:"Confirm import"})).toBeNull();
  expect(importFn).not.toHaveBeenCalled();
});

it("cancels an import preview without sending",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Import groups"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(['{"schemaVersion":1,"groups":[]}'],"groups.json",{type:"application/json"}));
  const cancel=await screen.findByRole("button",{name:"Cancel"});
  await userEvent.click(cancel);
  expect(importFn).not.toHaveBeenCalled();
});

it("ignores an import change event without a file",()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  fireEvent.click(screen.getByRole("button",{name:"Import groups"}));
  fireEvent.change(screen.getByTestId("group-import-file"),{target:{files:[]}});
  expect(importFn).not.toHaveBeenCalled();
});

it("shows empty draft for a new group selection",()=>{
  render(<GroupPanel {...props({groups:[],selectedGroupId:null,
    draft:{sourceGroupId:null,expectedRevision:null,name:"",description:"",intervalMs:250,items:[]}})}/>);
  expect(screen.queryByRole("button",{name:"Group (1)"})).toBeNull();
  expect(screen.getByRole("button",{name:"New group"})).toBeTruthy();
});

it("exports authoritative groups as a blob download on click",async()=>{
  const created:URL[]=[];
  const originalCreate=URL.createObjectURL;
  const originalRevoke=URL.revokeObjectURL;
  URL.createObjectURL=vi.fn(()=>{const url=new URL("blob:test-export");created.push(url);return url.href;}) as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL=vi.fn() as unknown as typeof URL.revokeObjectURL;
  try{
    render(<GroupPanel {...props({groups:[watchGroup()]})}/>);
    await userEvent.click(screen.getByRole("button",{name:"Export groups JSON"}));
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
  await userEvent.click(screen.getByRole("button",{name:"Import groups"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(['{"schemaVersion":1,"groups":{}}'],"bad-schema.json",{type:"application/json"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid");
  expect(screen.queryByRole("button",{name:"Confirm import"})).toBeNull();
  expect(importFn).not.toHaveBeenCalled();
});

it("closes the import preview when toggling the import button again",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Import groups"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(['{"schemaVersion":1,"groups":[]}'],"groups.json",{type:"application/json"}));
  expect(await screen.findByRole("button",{name:"Confirm import"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"Import groups"}));
  expect(screen.queryByRole("button",{name:"Confirm import"})).toBeNull();
  expect(importFn).not.toHaveBeenCalled();
});
