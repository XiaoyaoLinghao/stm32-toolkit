import {expect,it,vi} from "vitest";
import {fireEvent,render,screen,within} from "@testing-library/preact";
import {SourceCatalogPanel,SourceDiagnostics} from "../src/components/SourceCatalogPanel";
import type {SourceCatalogItem,SourceFileNode,SourceScopeNode} from "../src/api/contract";
import type {SourceCatalogState} from "../src/state/model";
import {sourcePage,sourceTreePage} from "./fixtures";

const file=(id:string,name:string):SourceFileNode=>({kind:"file",id:id.repeat(64),parentId:null,
 file:`Src/${name}`,name,scopeCount:name==="empty.c"?0:1,variableCount:name==="empty.c"?0:1});
const main=file("1","main.c"),safe=file("2","safe.c");
const scope:SourceScopeNode={kind:"scope",id:"4".repeat(64),parentId:main.id,file:main.file,
 name:"global",function:null,line:null,variableCount:1};
const leaf:SourceCatalogItem={id:"5".repeat(64),parentId:null,name:"counter",typeName:"int",file:main.file,
 line:8,column:3,scope:{kind:"global",function:null,path:[]},storage:"none",translationUnits:[main.file],
 selector:"counter",canAdd:true,reason:null,expandable:false,truncated:false,
 declaration:{kind:"global_definition",definitionSite:{file:main.file,line:8}}};
const source=():SourceCatalogState=>({query:"",initialized:true,generation:1n,contextKey:"context",
 tree:{...sourceTreePage(),total:2,items:[main,safe],nextCursor:null},branches:{
  [main.id]:{...sourceTreePage(),total:1,items:[scope],nextCursor:null}},
 scopePages:{[scope.id]:{...sourcePage(),total:1,items:[leaf],cursor:null}},children:{},lastAddedId:null});
const base=()=>({pending:{},failures:{},editBusy:false,onRetry:vi.fn(),onFirmware:vi.fn(),
 onSearch:vi.fn(),onChildren:vi.fn(),onSelect:vi.fn()});

it("lists files, then shows an opened file's globals directly without counts",()=>{
 const props=base();render(<SourceCatalogPanel source={source()} {...props}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 expect(within(region).getByRole("button",{name:"展开 Src"})).toHaveAttribute("aria-expanded","false");
 expect(within(region).queryByRole("button",{name:/main\.c/})).toBeNull();
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src"}));
 expect(within(region).getByRole("button",{name:/main\.c/})).toBeVisible();
 expect(within(region).getByRole("button",{name:/safe\.c/})).toBeVisible();
 expect(within(region).queryByRole("button",{name:/empty\.c/})).toBeNull();
 expect(within(region).getByRole("button",{name:"展开 Src/main.c"})).toHaveAttribute("title","Src/main.c");
 expect(within(region).getByText("main.c")).toBeVisible();
 expect(within(within(region).getByRole("button",{name:"展开 Src/main.c"})).queryByText("1 变量条目")).toBeNull();
 expect(within(region).queryByText("1 作用域")).toBeNull();
 expect(within(region).queryByRole("button",{name:"加入观测组草稿 counter"})).toBeNull();
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 expect(within(region).queryByRole("button",{name:"展开 global"})).toBeNull();
 expect(within(region).getByText("counter",{selector:"code"})).toBeVisible();
 expect(within(region).queryByText("已加载 1 / 1 个变量条目")).toBeNull();
 fireEvent.click(within(region).getByRole("button",{name:"加入观测组草稿 counter"}));
 expect(props.onSelect).toHaveBeenCalledWith(leaf);
 fireEvent.input(screen.getByPlaceholderText("搜索名称、文件或函数"),{target:{value:"safe"}});
 fireEvent.click(screen.getByRole("button",{name:"搜索"}));
 expect(props.onSearch).toHaveBeenCalledWith("safe");
});

it("loads only an opened file's globals once and leaves function scopes lazy",()=>{
 const props=base(),current=source();
 const functionScope:SourceScopeNode={...scope,id:"6".repeat(64),name:"tick",function:"tick"};
 const {rerender}=render(<SourceCatalogPanel source={{...current,branches:{},scopePages:{}}} {...props}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 expect(props.onChildren).not.toHaveBeenCalled();
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src"}));
 expect(props.onChildren).not.toHaveBeenCalled();
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 expect(props.onChildren).toHaveBeenCalledExactlyOnceWith(main.id);
 rerender(<SourceCatalogPanel source={{...current,branches:{
   [main.id]:{...sourceTreePage(),items:[scope,functionScope],total:2,nextCursor:null}},scopePages:{}}} {...props}/>);
 expect(props.onChildren).toHaveBeenCalledTimes(2);
 expect(props.onChildren).toHaveBeenLastCalledWith(scope.id);
 expect(within(region).getByRole("button",{name:"展开 tick"})).toBeVisible();
 rerender(<SourceCatalogPanel source={{...current,branches:{
   [main.id]:{...sourceTreePage(),items:[scope,functionScope],total:2,nextCursor:null}},scopePages:{}}} {...props}/>);
 expect(props.onChildren).toHaveBeenCalledTimes(2);
 fireEvent.click(within(region).getByRole("button",{name:"展开 tick"}));
 expect(props.onChildren).toHaveBeenLastCalledWith(functionScope.id);
 expect(props.onChildren).toHaveBeenCalledTimes(3);
});

it.each(["pending","failure"] as const)("does not auto-retry a global scope with a retained %s",kind=>{
 const props=base(),current=source(),requestScope=`catalog.source-node.${scope.id}` as const;
 const pending=kind==="pending"?{[requestScope]:{requestId:2n,scope:requestScope,summary:"global"}}:{};
 const failures=kind==="failure"?{[requestScope]:{ok:false as const,code:"MONITOR_SOURCE_CONTEXT_CHANGED",
   message:"changed",requestId:2n,recovery:"read-retry" as const,summary:"global"}}:{};
 render(<SourceCatalogPanel source={{...current,scopePages:{}}} {...props} pending={pending} failures={failures}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 expect(props.onChildren).not.toHaveBeenCalled();
 if(kind==="failure"){
   expect(within(region).getByRole("alert")).toHaveTextContent("MONITOR_SOURCE_CONTEXT_CHANGED");
   fireEvent.click(within(region).getByRole("button",{name:"重试上次操作"}));
   expect(props.onRetry).toHaveBeenCalledWith(requestScope,2n);
 }
});

it("shows indexed elements with full selectors and keeps container actions out of the row",()=>{
 const props=base(),current=source();
 const array:SourceCatalogItem={...leaf,id:"7".repeat(64),name:"PC_send2",selector:null,
   typeName:"uint8_t[100]",canAdd:false,expandable:true};
 const element:SourceCatalogItem={...leaf,id:"8".repeat(64),parentId:array.id,name:"53",
   selector:"PC_send2[53]",scope:{kind:"element",function:null,path:["PC_send2","53"]}};
 const scopePages={[scope.id]:{...sourcePage(),items:[array],total:1,cursor:null,nextCursor:null}};
 const children={[array.id]:{...sourcePage(),items:[element],total:1,cursor:null,nextCursor:null}};
 render(<SourceCatalogPanel source={{...current,scopePages,children}} {...props}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 expect(within(region).queryByRole("button",{name:"加入观测组草稿 PC_send2"})).toBeNull();
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c:8 / PC_send2"}));
 expect(within(region).getByText("[53]",{selector:"code"})).toHaveAttribute("aria-label","PC_send2[53]");
 expect(within(region).getByRole("button",{name:"加入观测组草稿 PC_send2[53]"})).toBeVisible();
});

it("keeps branch failure and retry local while another file remains available",()=>{
 const props=base(),current=source(),node=`catalog.source-node.${safe.id}` as const;
 render(<SourceCatalogPanel source={current} {...props} failures={{[node]:{ok:false,code:"MONITOR_SOURCE_CONTEXT_CHANGED",
  message:"changed",requestId:6n,recovery:"read-retry",summary:"safe"}}}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/safe.c"}));
 expect(within(region).getByRole("alert").textContent).toContain("MONITOR_SOURCE_CONTEXT_CHANGED");
 expect(within(region).getByText("counter",{selector:"code"})).toBeVisible();
 fireEvent.click(within(region).getByRole("button",{name:"重试上次操作"}));
 expect(props.onRetry).toHaveBeenCalledWith(node,6n);
});

it("resets expansion with a new directory generation",()=>{
 const props=base(),current=source();const {rerender}=render(<SourceCatalogPanel source={current} {...props}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 expect(within(region).getByText("counter",{selector:"code"})).toBeVisible();
 rerender(<SourceCatalogPanel source={{...current,generation:2n}} {...props}/>);
 expect(within(screen.getByRole("region",{name:"源码目录结果"})).queryByText("counter",{selector:"code"})).toBeNull();
 expect(within(screen.getByRole("region",{name:"源码目录结果"})).getByRole("button",{name:"展开 Src"})).toHaveAttribute("aria-expanded","false");
});

it("reveals matching folder paths for a search, keeps manual choices, and resets on the next result context",()=>{
 const props=base(),current=source();
 const found={...current,query:"testtime",generation:2n};
 const {rerender}=render(<SourceCatalogPanel source={found} {...props}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 expect(within(region).getByRole("button",{name:"收起 Src"})).toHaveAttribute("aria-expanded","true");
 expect(within(region).getByRole("button",{name:"展开 Src/main.c"})).toHaveAttribute("aria-expanded","false");
 expect(props.onChildren).not.toHaveBeenCalled();
 fireEvent.click(within(region).getByRole("button",{name:"收起 Src"}));
 expect(within(region).getByRole("button",{name:"展开 Src"})).toHaveAttribute("aria-expanded","false");
 rerender(<SourceCatalogPanel source={{...found,tree:{...found.tree!,total:3}}} {...props}/>);
 expect(within(region).getByRole("button",{name:"展开 Src"})).toHaveAttribute("aria-expanded","false");
 rerender(<SourceCatalogPanel source={{...found,generation:3n}} {...props}/>);
 expect(within(screen.getByRole("region",{name:"源码目录结果"})).getByRole("button",{name:"收起 Src"})).toHaveAttribute("aria-expanded","true");
 rerender(<SourceCatalogPanel source={{...current,generation:4n}} {...props}/>);
 expect(within(screen.getByRole("region",{name:"源码目录结果"})).getByRole("button",{name:"展开 Src"})).toHaveAttribute("aria-expanded","false");
});

it("shows a root failure with an in-place retry",()=>{
 const props=base();render(<SourceCatalogPanel source={{...source(),tree:null}} {...props}
  failures={{"catalog.source":{ok:false,code:"MONITOR_SOURCE_ENGINE_MISSING",message:"missing",
   requestId:5n,recovery:"read-retry",summary:"source"}}}/>);
 expect(screen.getByRole("alert").textContent).toContain("MONITOR_SOURCE_ENGINE_MISSING");
 fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
 expect(props.onRetry).toHaveBeenCalledWith("catalog.source",5n);
});

it("shows source statistics only in the global diagnostic section and refreshes explicitly",()=>{
 const props=base(),current=source();
 const tree={...current.tree!,coverage:{...current.tree!.coverage,complete:false,totalUnits:53,parsedUnits:2,
  issues:[{unit:"Main/Main.c",code:"MONITOR_SOURCE_INDEX_FAILED",message:"Clang failed"}],
  compiledDebug:{available:true,variableCount:1169,functionCount:463,fileCount:47}}};
 const sourceState={...current,tree};
 render(<><SourceCatalogPanel source={sourceState} {...props}/><SourceDiagnostics source={sourceState}/></>);
 const details=document.querySelector(".source-diagnostics")!;
 expect(within(screen.getByRole("region",{name:"源码目录结果"})).queryByText("已加载 2 / 2 个文件")).toBeNull();
 expect(details).toHaveTextContent("已加载 2 / 2 个文件");
 expect(screen.queryByText(/搜索结果：/)).toBeNull();
 expect(details).toHaveTextContent("固件调试元数据统计（不代表当前目录可观测条目）：1169 个变量及参数声明、463 个函数、47 个文件");
 expect(details).toHaveTextContent("源码补充解析 2 / 53");
 expect(details).toHaveTextContent("源码目录覆盖不完整，部分声明尚未收录。");
 expect(details.querySelectorAll("li")).toHaveLength(1);
 fireEvent.click(screen.getByRole("button",{name:"刷新源码目录"}));
 expect(props.onSearch).toHaveBeenCalledWith("",true);
});

it("shows a proved extern definition and a named rebuild warning without extra navigation",()=>{
 const props=base(),current=source(),extern={...leaf,name:"testtime",storage:"extern" as const,
  declaration:{kind:"extern_declaration" as const,definitionSite:{file:"Src/timer.c",line:7}}};
 const tree={...current.tree!,coverage:{...current.tree!.coverage,complete:false,
  issues:[{unit:"Inc/timer.h",code:"MONITOR_SOURCE_UNTRACKED_AST",message:"legacy snapshot omitted header"}]}};
 const scopePages={[scope.id]:{...sourcePage(),total:1,items:[extern],cursor:null}};
 const sourceState={...current,tree,scopePages};
 render(<><SourceCatalogPanel source={sourceState} {...props}/><SourceDiagnostics source={sourceState}/></>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 fireEvent.click(region.querySelector(".source-row-detail summary")!);
 expect(within(region).getByText("外部声明",{exact:false})).toBeVisible();
 expect(within(region).getByText("对应定义 Src/timer.c:7")).toBeVisible();
 expect(screen.getByText(/Inc\/timer.h：旧构建快照未收录/)).toBeVisible();
});

it("explains a new-policy outside-snapshot path requires project declarations before rebuilding",()=>{
 const props=base(),current=source();
 const tree={...current.tree!,coverage:{...current.tree!.coverage,complete:false,
  issues:[{unit:"Extra/more.h",code:"MONITOR_SOURCE_OUTSIDE_SNAPSHOT_POLICY",message:"outside policy"}]}};
 const sourceState={...current,tree};
 render(<><SourceCatalogPanel source={sourceState} {...props}/><SourceDiagnostics source={sourceState}/></>);
 expect(screen.getByText("Extra/more.h：当前源码快照未收录；请核对工程声明和包含目录，补齐后干净重建。"))
  .toBeVisible();
 expect(screen.queryByText(/旧构建快照未收录/)).toBeNull();
});

it("does not call an incomplete empty result proof that source has no variables",()=>{
 const props=base(),current=source();
 const tree={...current.tree!,total:0,items:[],coverage:{...current.tree!.coverage,
  complete:false,totalUnits:53,parsedUnits:2,issues:[],
  compiledDebug:{available:false,variableCount:0,functionCount:0,fileCount:0}}};
 const sourceState={...current,tree};
 render(<><SourceCatalogPanel source={sourceState} {...props}/><SourceDiagnostics source={sourceState}/></>);
 expect(screen.getAllByText("暂无可用源码信息；不能据此断定源码没有变量。").length).toBeGreaterThan(0);
 expect(screen.getByText("源码目录覆盖不完整，部分声明尚未收录。")).toBeVisible();
});

it("explains missing firmware before a search miss even with complete source parsing",()=>{
 const props=base(),current=source();
 const tree={...current.tree!,total:0,items:[],identity:{...current.tree!.identity,buildId:null},
  coverage:{...current.tree!.coverage,complete:true,totalUnits:1,parsedUnits:1,issues:[]}};
 render(<SourceCatalogPanel source={{...current,query:"counter",tree}} {...props}/>);
 expect(screen.getAllByText("暂无可用源码信息；不能据此断定源码没有变量。").length).toBeGreaterThan(0);
 expect(screen.queryByText("没有符合搜索条件的可观测变量条目。")).toBeNull();
});

it("explains offline eligibility and distinguishes empty directory from search miss",()=>{
 const props=base(),current=source(),pending={...leaf,canAdd:false,reason:"probe_required" as const};
 const scopePages={[scope.id]:{...sourcePage(),total:1,items:[pending],cursor:null}};
 const {rerender}=render(<SourceCatalogPanel source={{...current,scopePages}} {...props}/>);
 const region=screen.getByRole("region",{name:"源码目录结果"});
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src"}));
 fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
 expect(within(region).getByText("待连接")).toBeVisible();
 expect(within(region).queryByRole("button",{name:"加入观测组草稿 counter"})).toBeNull();
 const emptyTree={...current.tree!,items:[],total:0,
  identity:{...current.tree!.identity,buildId:"build"}};
 rerender(<SourceCatalogPanel source={{...current,tree:emptyTree}} {...props}/>);
 expect(screen.getByText("当前固件与源码未证明可观测变量条目；这不表示程序没有变量。")).toBeVisible();
 rerender(<SourceCatalogPanel source={{...current,query:"none",tree:emptyTree}} {...props}/>);
 expect(screen.getByText("没有符合搜索条件的可观测变量条目。")).toBeVisible();
});
