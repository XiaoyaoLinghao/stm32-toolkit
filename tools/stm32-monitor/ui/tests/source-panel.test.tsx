import {expect,it,vi} from "vitest";
import {fireEvent,render,screen} from "@testing-library/preact";
import {SourceCatalogPanel} from "../src/components/SourceCatalogPanel";
import type {SourceCatalogItem} from "../src/api/contract";
import type {SourceCatalogState} from "../src/state/model";
import {sourcePage} from "./fixtures";

const leaf=(id:string,name:string,reason:SourceCatalogItem["reason"],kind:SourceCatalogItem["scope"]["kind"]):SourceCatalogItem=>({
 id:id.repeat(64),parentId:null,name,typeName:"int",file:"Src/main.c",line:8,column:3,
 scope:{kind,function:kind==="local"?"sample":null,path:kind==="local"?["block@1"]:[]},
 storage:"none",translationUnits:["Src/main.c"],selector:reason===null?name:null,
 canAdd:reason===null,reason,expandable:false,truncated:false,
});
const source=(items:readonly SourceCatalogItem[],nextCursor:string|null=null):SourceCatalogState=>({
 query:"",initialized:true,generation:1n,contextKey:"context",page:{...sourcePage(),items,total:items.length,nextCursor,cursor:null},
 children:{},lastAddedId:null,
});

it("browses source files and functions without a probe, with reasoned disabled rows and search",()=>{
 const search=vi.fn(),select=vi.fn(),local=leaf("c","gpio","frame_required","local"),global=leaf("d","counter",null,"global");
 render(<SourceCatalogPanel source={source([local,global],"next")} pending={false} childPending={false} selectionPending={false}
   failures={{}} onRetry={vi.fn()} onFirmware={vi.fn()}
   editBusy={false} onSearch={search} onNext={vi.fn()} onChildren={vi.fn()} onSelect={select}/>);
 expect(screen.getByText("已加载 2 / 2 项 · 已解析 1 / 1 个编译单元")).toBeTruthy();
 fireEvent.click(screen.getByText(/Src\/main.c · 已加载/));
 fireEvent.click(screen.getByText(/sample · 1/));
 const disabled=screen.getByRole("button",{name:"加入观测组草稿 gpio"}) as HTMLButtonElement;
 expect(disabled.disabled).toBe(true);
 expect(screen.getByText("局部变量需要运行栈帧")).toBeTruthy();
 fireEvent.click(screen.getByText(/全局／文件作用域 · 1/));
 fireEvent.click(screen.getByRole("button",{name:"加入观测组草稿 counter"}));
 expect(select).toHaveBeenCalledWith(global);
 fireEvent.input(screen.getByPlaceholderText("搜索名称、文件或函数"),{target:{value:"gpio"}});
 fireEvent.click(screen.getByRole("button",{name:"搜索"}));
 expect(search).toHaveBeenCalledWith("gpio");
});

it("shows partial coverage, bounded children, and an explicit local retry",()=>{
 const aggregate={...leaf("e","samples","aggregate","global"),selector:"samples",expandable:true,truncated:true};
 const base=source([aggregate]);
 const state:SourceCatalogState={...base,page:{...base.page!,coverage:{complete:false,totalUnits:3,parsedUnits:2,
   issues:[{unit:"Src/broken.c",code:"MONITOR_SOURCE_INDEX_FAILED",message:"failed"}],truncated:true}}};
 const search=vi.fn(),children=vi.fn();
 render(<SourceCatalogPanel source={state} pending={false} childPending={false} selectionPending={false} editBusy={false}
   failures={{}} onRetry={vi.fn()} onFirmware={vi.fn()}
   onSearch={search} onNext={vi.fn()} onChildren={children} onSelect={vi.fn()}/>);
 expect(screen.getByText("部分编译单元未解析，当前列表不完整。")).toBeTruthy();
 fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
 expect(search).toHaveBeenCalledWith("");
 fireEvent.click(screen.getByText(/Src\/main.c · 已加载/));
 fireEvent.click(screen.getByText(/全局／文件作用域 · 1/));
 fireEvent.click(screen.getByRole("button",{name:"展开 samples"}));
 expect(children).toHaveBeenCalledWith(aggregate.id);
});

it("shows a missing-engine failure and an in-place retry with firmware fallback",()=>{
 const retry=vi.fn(),firmware=vi.fn(),empty:SourceCatalogState={...source([]),page:null};
 render(<SourceCatalogPanel source={empty} pending={false} childPending={false} selectionPending={false}
   editBusy={false} failures={{"catalog.source":{ok:false,code:"MONITOR_SOURCE_ENGINE_MISSING",message:"missing",
     requestId:5n,recovery:"read-retry",summary:"source"}}} onRetry={retry} onFirmware={firmware}
   onSearch={vi.fn()} onNext={vi.fn()} onChildren={vi.fn()} onSelect={vi.fn()}/>);
 expect(screen.getByRole("alert").textContent).toContain("MONITOR_SOURCE_ENGINE_MISSING");
 fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
 expect(retry).toHaveBeenCalledWith("catalog.source",5n);
 fireEvent.click(screen.getByRole("button",{name:"查看固件变量与寄存器"}));
 expect(firmware).toHaveBeenCalled();
});

it("shows a child-page failure without leaving an endless loading message",()=>{
 const aggregate={...leaf("e","samples","aggregate","global"),selector:"samples",expandable:true};
 const retry=vi.fn();
 render(<SourceCatalogPanel source={source([aggregate])} pending={false} childPending={false} selectionPending={false}
   editBusy={false} failures={{"catalog.source-child":{ok:false,code:"MONITOR_SOURCE_CONTEXT_CHANGED",message:"changed",
     requestId:6n,recovery:"read-retry",summary:"children"}}} onRetry={retry} onFirmware={vi.fn()}
   onSearch={vi.fn()} onNext={vi.fn()} onChildren={vi.fn()} onSelect={vi.fn()}/>);
 fireEvent.click(screen.getByText(/Src\/main.c · 已加载/));
 fireEvent.click(screen.getByText(/全局／文件作用域 · 1/));
 fireEvent.click(screen.getByRole("button",{name:"展开 samples"}));
 expect(screen.getByRole("alert").textContent).toContain("MONITOR_SOURCE_CONTEXT_CHANGED");
 fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
 expect(retry).toHaveBeenCalledWith("catalog.source-child",6n);
});
