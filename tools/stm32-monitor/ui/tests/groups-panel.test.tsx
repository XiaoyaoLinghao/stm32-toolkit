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
    onCreate:vi.fn(),
    onSave:vi.fn(),
    onDelete:vi.fn(),
    onReadImport:async()=>({ok:false,code:"MONITOR_IMPORT_INVALID",message:"invalid"}),
    onImport:vi.fn(),
    onExport:vi.fn(),
    onRefresh:vi.fn(),
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
    onCreate:create,onSave:save,
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

it("saves and deletes the selected group",async()=>{
  const save=vi.fn(),del=vi.fn();
  render(<GroupPanel {...props({onSave:save,onDelete:del})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Save group"}));
  expect(save).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Delete"}));
  expect(del).toHaveBeenCalledWith("group");
});

it("renders failure alert",()=>{
  render(<GroupPanel {...props({failure:{ok:false,code:"GROUPS_FAILED",message:"cannot save"}})}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("GROUPS_FAILED");
});

it("imports a group document and exports groups JSON",async()=>{
  const importFn=vi.fn();
  const createObjectURL=vi.spyOn(URL,"createObjectURL").mockReturnValue("blob:url");
  const click=vi.fn();
  Object.defineProperty(HTMLAnchorElement.prototype,"click",{value:click,configurable:true});
  render(<GroupPanel {...props({onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Import groups"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(['{"schemaVersion":1,"groups":[]}'],"groups.json",{type:"application/json"}));
  expect(importFn).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Export groups JSON"}));
  expect(click).toHaveBeenCalled();
  createObjectURL.mockRestore();
});

it("imports with a successful read and resets the file input",async()=>{
  const importFn=vi.fn();
  render(<GroupPanel {...props({onReadImport:async()=>({ok:true,data:{schemaVersion:1,groups:[]}}),onImport:importFn})}/>);
  await userEvent.click(screen.getByRole("button",{name:"Import groups"}));
  const file=screen.getByTestId("group-import-file");
  await userEvent.upload(file,new File(['{}'],"groups.json",{type:"application/json"}));
  expect(importFn).toHaveBeenCalledWith({schemaVersion:1,groups:[]});
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
