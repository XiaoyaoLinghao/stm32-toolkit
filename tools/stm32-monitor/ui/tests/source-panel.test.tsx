import {expect,it,vi} from "vitest";
import {fireEvent,render,screen,within} from "@testing-library/preact";
import {SourceCatalogPanel} from "../src/components/SourceCatalogPanel";
import type {SourceCatalogItem,SourceFileNode,SourceScopeNode} from "../src/api/contract";
import type {SourceCatalogState} from "../src/state/model";
import {sourcePage,sourceTreePage} from "./fixtures";

const file=(id:string,name:string):SourceFileNode=>({kind:"file",id:id.repeat(64),parentId:null,
 file:`Src/${name}`,name,scopeCount:name==="empty.c"?0:1,variableCount:name==="empty.c"?0:1});
const main=file("1","main.c"),safe=file("2","safe.c"),empty=file("3","empty.c");
const scope:SourceScopeNode={kind:"scope",id:"4".repeat(64),parentId:main.id,file:main.file,
 name:"global",function:null,line:null,variableCount:1};
const leaf:SourceCatalogItem={id:"5".repeat(64),parentId:null,name:"counter",typeName:"int",file:main.file,
 line:8,column:3,scope:{kind:"global",function:null,path:[]},storage:"none",translationUnits:[main.file],
 selector:"counter",canAdd:true,reason:null,expandable:false,truncated:false};
const source=():SourceCatalogState=>({query:"",initialized:true,generation:1n,contextKey:"context",
 tree:{...sourceTreePage(),total:3,items:[main,safe,empty],nextCursor:null},branches:{
  [main.id]:{...sourceTreePage(),total:1,items:[scope],nextCursor:null}},
 scopePages:{[scope.id]:{...sourcePage(),total:1,items:[leaf],cursor:null}},children:{},lastAddedId:null});
const base=()=>({pending:{},failures:{},editBusy:false,onRetry:vi.fn(),onFirmware:vi.fn(),
 onSearch:vi.fn(),onChildren:vi.fn(),onSelect:vi.fn()});

it("lists all source files before loading leaves, then expands only the requested scope",()=>{
 const props=base();render(<SourceCatalogPanel source={source()} {...props}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 expect(within(region).getByRole("button",{name:/main\.c/})).toBeVisible();
 expect(within(region).getByRole("button",{name:/safe\.c/})).toBeVisible();
 expect(within(region).getByRole("button",{name:/empty\.c/})).toBeVisible();
 expect(within(region).queryByRole("button",{name:"加入观测组草稿 counter"})).toBeNull();
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 global"}));
 fireEvent.click(within(region).getByRole("button",{name:"加入观测组草稿 counter"}));
 expect(props.onSelect).toHaveBeenCalledWith(leaf);
 fireEvent.input(screen.getByPlaceholderText("搜索名称、文件或函数"),{target:{value:"safe"}});
 fireEvent.click(screen.getByRole("button",{name:"搜索"}));
 expect(props.onSearch).toHaveBeenCalledWith("safe");
});

it("keeps branch failure and retry local while another file remains available",()=>{
 const props=base(),current=source(),node=`catalog.source-node.${safe.id}` as const;
 render(<SourceCatalogPanel source={current} {...props} failures={{[node]:{ok:false,code:"MONITOR_SOURCE_CONTEXT_CHANGED",
  message:"changed",requestId:6n,recovery:"read-retry",summary:"safe"}}}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/safe.c"}));
 expect(within(region).getByRole("alert").textContent).toContain("MONITOR_SOURCE_CONTEXT_CHANGED");
 expect(within(region).getByRole("button",{name:"展开 global"})).toBeVisible();
 fireEvent.click(within(region).getByRole("button",{name:"重试上次操作"}));
 expect(props.onRetry).toHaveBeenCalledWith(node,6n);
});

it("resets expansion with a new directory generation",()=>{
 const props=base(),current=source();const {rerender}=render(<SourceCatalogPanel source={current} {...props}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 expect(within(region).getByRole("button",{name:"展开 global"})).toBeVisible();
 rerender(<SourceCatalogPanel source={{...current,generation:2n}} {...props}/>);
 expect(within(screen.getByRole("region",{name:"源码目录结果"})).queryByRole("button",{name:"展开 global"})).toBeNull();
});

it("shows a root failure with an in-place retry",()=>{
 const props=base();render(<SourceCatalogPanel source={{...source(),tree:null}} {...props}
  failures={{"catalog.source":{ok:false,code:"MONITOR_SOURCE_ENGINE_MISSING",message:"missing",
   requestId:5n,recovery:"read-retry",summary:"source"}}}/>);
 expect(screen.getByRole("alert").textContent).toContain("MONITOR_SOURCE_ENGINE_MISSING");
 fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
 expect(props.onRetry).toHaveBeenCalledWith("catalog.source",5n);
});
