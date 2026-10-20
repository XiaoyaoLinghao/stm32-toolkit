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
 selector:"counter",canAdd:true,reason:null,expandable:false,truncated:false,
 declaration:{kind:"global_definition",definitionSite:{file:main.file,line:8}}};
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
 expect(within(region).getByText("全局定义")).toBeVisible();
 expect(within(region).getByText("可采样")).toBeVisible();
 expect(within(region).getByText("已加载 1 / 1 条声明")).toBeVisible();
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

it("labels compiled debug facts ahead of incomplete AST details and refreshes explicitly",()=>{
 const props=base(),current=source();
 const tree={...current.tree!,coverage:{...current.tree!.coverage,complete:false,totalUnits:53,parsedUnits:2,
  issues:[{unit:"Main/Main.c",code:"MONITOR_SOURCE_INDEX_FAILED",message:"Clang failed"}],
  compiledDebug:{available:true,variableCount:1169,functionCount:463,fileCount:47}}};
 render(<SourceCatalogPanel source={{...current,tree}} {...props}/>);
 const status=screen.getAllByRole("status").map(item=>item.textContent??"");
 expect(status[0]).toContain("已按当前固件调试信息列出变量");
 expect(status[1]).toContain("源码补充解析 2 / 53");
 expect(screen.getByText("源码目录覆盖不完整，部分声明尚未收录。")).toBeVisible();
 expect(screen.getByText("目录覆盖与解析详情")).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"刷新源码目录"}));
 expect(props.onSearch).toHaveBeenCalledWith("",true);
});

it("shows a proved extern definition and a named rebuild warning without extra navigation",()=>{
 const props=base(),current=source(),extern={...leaf,name:"testtime",storage:"extern" as const,
  declaration:{kind:"extern_declaration" as const,definitionSite:{file:"Src/timer.c",line:7}}};
 const tree={...current.tree!,coverage:{...current.tree!.coverage,complete:false,
  issues:[{unit:"Inc/timer.h",code:"MONITOR_SOURCE_UNTRACKED_AST",message:"legacy snapshot omitted header"}]}};
 const scopePages={[scope.id]:{...sourcePage(),total:1,items:[extern],cursor:null}};
 render(<SourceCatalogPanel source={{...current,tree,scopePages}} {...props}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 global"}));
 expect(within(region).getByText("外部声明")).toBeVisible();
 expect(within(region).getByText("对应定义 Src/timer.c:7")).toBeVisible();
 fireEvent.click(screen.getByText("目录覆盖与解析详情"));
 expect(screen.getByText(/Inc\/timer.h：旧构建快照未收录/)).toBeVisible();
});

it("explains a new-policy outside-snapshot path requires project declarations before rebuilding",()=>{
 const props=base(),current=source();
 const tree={...current.tree!,coverage:{...current.tree!.coverage,complete:false,
  issues:[{unit:"Extra/more.h",code:"MONITOR_SOURCE_OUTSIDE_SNAPSHOT_POLICY",message:"outside policy"}]}};
 render(<SourceCatalogPanel source={{...current,tree}} {...props}/>);
 fireEvent.click(screen.getByText("目录覆盖与解析详情"));
 expect(screen.getByText("Extra/more.h：当前源码快照未收录；请核对工程声明和包含目录，补齐后干净重建。"))
  .toBeVisible();
 expect(screen.queryByText(/旧构建快照未收录/)).toBeNull();
});

it("does not call an incomplete empty file tree proof that source has no variables",()=>{
 const props=base(),current=source();
 const tree={...current.tree!,total:1,items:[empty],coverage:{...current.tree!.coverage,
  complete:false,totalUnits:53,parsedUnits:2,issues:[],
  compiledDebug:{available:false,variableCount:0,functionCount:0,fileCount:0}}};
 render(<SourceCatalogPanel source={{...current,tree}} {...props}/>);
 expect(screen.getByText("暂无可用源码信息；不能据此断定源码没有变量。")).toBeVisible();
});
