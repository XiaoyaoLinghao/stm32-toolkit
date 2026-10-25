import {Buffer} from "node:buffer";
import {createHash} from "node:crypto";
import {expect,test} from "@playwright/test";
import {openMonitor,startMonitor} from "./conftest";

test.describe("STM32 Monitor user workflow",()=>{
  let monitor:{url:string;accessUrl:string;stop:()=>void};

  test.beforeEach(async()=>{
    monitor=await startMonitor(process.cwd(),process.env.STM32_MONITOR_EVIDENCE??process.cwd());
  });
  test.afterEach(async()=>{
    monitor.stop();
  });

  async function freshPage(page:import("@playwright/test").Page){
    await openMonitor(page,monitor.accessUrl);
    await expect(page.getByLabel("STM32 监视器")).toBeAttached();
    await expect(page.getByText("Fake Project · STM32F407VG",{exact:true})).toBeVisible();
  }

  function groupDrawer(page:import("@playwright/test").Page){
    return page.getByRole("dialog",{name:"观测组"});
  }

  async function openGroupDrawer(page:import("@playwright/test").Page){
    if(!await groupDrawer(page).isVisible())
      await page.getByRole("button",{name:"编辑并保存",exact:true}).click();
    await expect(groupDrawer(page)).toBeVisible();
  }

  async function closeGroupDrawer(page:import("@playwright/test").Page){
    if(await groupDrawer(page).isVisible())
      await page.getByRole("button",{name:"关闭观测组",exact:true}).click();
    await expect(groupDrawer(page)).toBeHidden();
  }

  async function connectProbe(page:import("@playwright/test").Page){
    await page.getByRole("button",{name:"连接与固件详情"}).click();
    await page.getByRole("button",{name:"连接",exact:true}).click();
    // A successful write closes the device drawer; the receipt stays visible.
    await expect(page.getByRole("status",{name:"探针操作结果"})).toContainText("探针连接成功");
    await page.getByRole("button",{name:"连接与固件详情"}).click();
    await expect(page.getByText(/已连接：probe-a/)).toBeVisible();
    await page.getByRole("button",{name:"关闭设备详情",exact:true}).click();
  }

  async function addWatch(page:import("@playwright/test").Page,expression:string){
    await page.getByRole("tab",{name:"源码目录",exact:true}).click();
    const search=page.getByLabel("搜索",{exact:true});
    await search.fill(expression);
    await search.press("Enter");
    const file=page.getByRole("button",{name:"展开 firmware/main.c",exact:true});
    await expect(file).toBeVisible();
    await file.click();
    const add=page.getByRole("button",{name:`加入观测组草稿 ${expression}`,exact:true});
    await expect(add).toBeVisible();
    await add.click();
    await expect(page.getByText("已加入组草稿（尚未保存）",{exact:true})).toBeVisible();
  }

  async function newDraft(page:import("@playwright/test").Page){
    await openGroupDrawer(page);
    await page.getByRole("button",{name:"新建观测组"}).click();
    await expect(page.getByRole("heading",{name:"新建观测组草稿"})).toBeVisible();
    await closeGroupDrawer(page);
  }

  async function createGroup(page:import("@playwright/test").Page,name:string,expression:string){
    await newDraft(page);
    await addWatch(page,expression);
    await openGroupDrawer(page);
    await page.getByLabel("名称",{exact:true}).fill(name);
    const create=page.getByRole("button",{name:"创建观测组",exact:true});
    await expect(create).toBeEnabled();
    await create.click();
    await expect(page.getByRole("button",{name:`${name} (1)`,exact:true})).toBeVisible();
  }

  test("fresh workspace starts with zero named groups",async({page})=>{
    await freshPage(page);
    await openGroupDrawer(page);
    const section=page.getByRole("region",{name:"观测组"});
    await section.getByRole("button",{name:"新建观测组"}).click();
    await expect(section.getByRole("heading",{name:"新建观测组草稿"})).toBeVisible();
    await expect(section.getByRole("button",{name:"创建观测组"})).toBeDisabled();
  });

  test("creates a group from the blank draft",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await createGroup(page,"Motor Watch","counter");
    await expect(page.getByRole("button",{name:"Motor Watch (1)",exact:true})).toBeVisible();
  });

  test("edits an existing group via expected revision save",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await createGroup(page,"Motor Watch","counter");
    await page.getByLabel("名称",{exact:true}).fill("Renamed Watch");
    await page.getByRole("button",{name:"保存观测组",exact:true}).click();
    await expect(page.getByRole("button",{name:"Renamed Watch (1)"})).toBeVisible();
  });

  test("deletes a group only after explicit confirmation",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await createGroup(page,"Motor Watch","counter");
    await page.getByRole("button",{name:"删除"}).click();
    await expect(page.getByRole("button",{name:"确认删除"})).toBeVisible();
    await page.getByRole("button",{name:"取消"}).click();
    await expect(page.getByRole("button",{name:"Motor Watch (1)"})).toBeVisible();
    await page.getByRole("button",{name:"删除"}).click();
    await page.getByRole("button",{name:"确认删除"}).click();
    await expect(page.getByRole("button",{name:"Motor Watch (1)"})).not.toBeVisible();
  });

  test("imports a group document after preview and second confirmation",async({page})=>{
    await freshPage(page);
    await openGroupDrawer(page);
    await page.getByRole("button",{name:"导入观测组"}).click();
    await page.getByTestId("group-import-file").setInputFiles({
      name:"groups.json",
      mimeType:"application/json",
      buffer:Buffer.from(
        JSON.stringify({
          schemaVersion:1,
          groups:[{name:"Imported",description:"",intervalMs:5000,items:[]}],
        }),
      ),
    });
    await expect(page.getByText(/将导入 1 个观测组/)).toBeVisible();
    await page.getByRole("button",{name:"确认导入"}).click();
    await expect(page.getByRole("button",{name:"Imported (0)"})).toBeVisible();
  });

  test("rejects an invalid import without sending it",async({page})=>{
    await freshPage(page);
    await openGroupDrawer(page);
    await page.getByRole("button",{name:"导入观测组"}).click();
    await page.getByTestId("group-import-file").setInputFiles({
      name:"bad.json",
      mimeType:"application/json",
      buffer:Buffer.from('{"schemaVersion":1,"groups":{}}'),
    });
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button",{name:"确认导入"})).not.toBeVisible();
  });

  test("exports authoritative groups as a blob download",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await createGroup(page,"Motor Watch","counter");
    const downloadPromise=page.waitForEvent("download");
    await page.getByRole("button",{name:"导出观测组 JSON"}).click();
    const download=await downloadPromise;
    const stream=await download.createReadStream();
    const body=stream===null?"":(await readStream(stream)).toString("utf-8");
    const parsed=JSON.parse(body);
    expect(parsed.schemaVersion).toBe(1);
    expect(parsed.groups.length).toBe(1);
    expect(parsed.groups[0]!.name).toBe("Motor Watch");
    expect(parsed.groups[0]!.items[0]).toEqual({kind:"variable",expression:"counter"});
    expect(JSON.stringify(parsed)).not.toContain("groupId");
    expect(JSON.stringify(parsed)).not.toContain("revision");
  });

  test("starts pauses resumes and stops sampling per API contract",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await createGroup(page,"Motor Watch","counter");
    await closeGroupDrawer(page);
    const state=page.getByLabel("采样控制").getByRole("status");
    await page.getByRole("button",{name:"开始采样"}).click();
    await expect(state).toContainText("采样中");
    await page.getByRole("button",{name:"暂停采样"}).click();
    await expect(state).toContainText("已暂停");
    await page.getByRole("button",{name:"继续采样"}).click();
    await expect(state).toContainText("采样中");
    await page.getByRole("button",{name:"停止采样"}).click();
    await expect(state).toContainText("未采样");
  });

  test("one failed item does not block the live table value",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await newDraft(page);
    await addWatch(page,"counter");
    await addWatch(page,"faulty");
    await openGroupDrawer(page);
    await page.getByLabel("名称",{exact:true}).fill("Motor Watch");
    await page.getByRole("button",{name:"创建观测组",exact:true}).click();
    await closeGroupDrawer(page);
    await page.getByRole("button",{name:"开始采样"}).click();
    await expect(page.getByLabel("采样控制").getByRole("status")).toContainText("采样中");
    const table=page.getByRole("region",{name:"最新数值"}).getByRole("table");
    await expect(table).toContainText("counter");
    await expect(table).toContainText("读取失败");
    await expect(table).toContainText("faulty");
  });

  test("keeps catalog results inside a local scroller at 320 pixels",async({page})=>{
    await page.setViewportSize({width:320,height:700});
    // The header project summary is intentionally hidden at this viewport, so
    // this layout scenario checks only the shell and the catalog scroller.
    await openMonitor(page,monitor.accessUrl);
    await expect(page.getByLabel("STM32 监视器")).toBeAttached();
    await connectProbe(page);
    await page.getByRole("tab",{name:"固件变量与寄存器",exact:true}).click();
    await page.getByLabel("搜索",{exact:true}).fill("counter");
    await page.getByRole("button",{name:"搜索/加载",exact:true}).click();
    const results=page.getByRole("region",{name:"目录搜索结果"});
    await expect(results.getByText("counter",{exact:true})).toBeVisible();
    const widths=await page.evaluate(()=>({page:document.documentElement.scrollWidth,viewport:window.innerWidth}));
    expect(widths.page).toBeLessThanOrEqual(widths.viewport);
    expect(await results.evaluate(element=>element.scrollWidth>element.clientWidth)).toBe(true);
  });

  test("queries UTC history, retains a manual export draft, and downloads the submitted task",async({page})=>{
    // This route supplies only the fake runtime's missing export capability;
    // history, navigation and UI state still run through the normal browser app.
    const submitted:string[]=[];
    const artifacts=new Map<string,{exportId:string;format:"csv"|"jsonl";sha256:string;bytes:number;valueCount:number}>();
    const files=new Map<string,string>();
    let nextId=1;
    const envelope=(operation:string,data:unknown)=>JSON.stringify({protocol:"stm32-toolkit-monitor/1",
      toolkitVersion:"1.0.0",monitorVersion:"1.0.0",ok:true,operation,code:"OK",message:"",data,details:{}});
    await page.route(/\/api\/v1\/exports(?:\/.*)?$/,async route=>{
      const request=route.request(),path=new URL(request.url()).pathname;
      if(request.method()==="POST"&&path==="/api/v1/exports"){
        const body=request.postData()??"";
        submitted.push(body);
        const format=JSON.parse(body).format as "csv"|"jsonl";
        const payload=format==="csv"
          ?"captured_at_utc,selector,value\n2026-08-10T00:00:01Z,counter,1\n"
          :'{"capturedAtUtc":"2026-08-10T00:00:01Z","selector":"counter","value":1}\n';
        const artifact={exportId:`e${nextId++}`,format,sha256:createHash("sha256").update(payload).digest("hex"),
          bytes:Buffer.byteLength(payload),valueCount:1};
        artifacts.set(artifact.exportId,artifact);
        files.set(artifact.exportId,payload);
        await route.fulfill({status:200,contentType:"application/json",body:envelope("monitor.exports.create",artifact)});
        return;
      }
      const match=/^\/api\/v1\/exports\/(e\d+)(\/download)?$/.exec(path);
      const artifact=match===null?undefined:artifacts.get(match[1]!);
      if(artifact===undefined){await route.abort();return;}
      if(match?.[2]!==undefined){
        await route.fulfill({status:200,headers:{"Content-Type":artifact.format==="csv"?"text/csv":"application/x-ndjson",
          "Content-Disposition":`attachment; filename="${artifact.exportId}.${artifact.format}"`},body:files.get(artifact.exportId)!});
        return;
      }
      await route.fulfill({status:200,contentType:"application/json",body:envelope("monitor.exports.get",artifact)});
    });
    await freshPage(page);
    await page.getByRole("button",{name:"历史记录"}).click();
    // datetime-local values are canonical: a zero seconds/fraction component is
    // omitted by the DOM, and Playwright rejects fills the DOM would normalize.
    await page.getByLabel("开始时间（UTC）",{exact:true}).fill("2026-08-10T00:00");
    await page.getByLabel("结束时间（UTC）",{exact:true}).fill("2026-08-10T00:00:02");
    await page.getByRole("button",{name:"查询历史"}).click();
    await expect(page.getByText("此范围内暂无历史记录。")).toBeVisible();
    const exportStart=page.getByLabel("导出开始时间（UTC）");
    const exportEnd=page.getByLabel("导出结束时间（UTC）");
    await expect(exportStart).toHaveValue(/^2026-08-10T00:00$/);
    await exportStart.fill("2026-08-10T00:00:01");
    await exportEnd.fill("2026-08-10T00:00:04");
    await page.getByRole("button",{name:"实时监视"}).click();
    await page.getByRole("button",{name:"历史记录"}).click();
    await expect(exportStart).toHaveValue(/^2026-08-10T00:00:01$/);
    await page.getByRole("button",{name:"创建 CSV 导出"}).click();
    await page.getByRole("button",{name:"确认导出"}).click();
    await expect(page.getByText(/提交时范围.*00:00:01.*00:00:04/)).toBeVisible();
    expect(submitted).toHaveLength(1);
    expect(submitted[0]).toContain((BigInt(Date.parse("2026-08-10T00:00:01Z"))*1_000_000n).toString());
    expect(submitted[0]).toContain('"format":"csv"');
    await page.getByLabel("开始时间（UTC）",{exact:true}).fill("2026-08-10T00:00:10");
    await page.getByLabel("结束时间（UTC）",{exact:true}).fill("2026-08-10T00:00:12");
    await page.getByRole("button",{name:"查询历史"}).click();
    await expect(page.getByText("查询范围已更新，保留当前导出范围。")).toBeVisible();
    await expect(exportStart).toHaveValue(/^2026-08-10T00:00:01$/);
    await expect(page.getByText(/提交时范围.*00:00:01.*00:00:04/)).toBeVisible();
    await page.getByRole("button",{name:"使用查询范围"}).click();
    await expect(exportStart).toHaveValue(/^2026-08-10T00:00:10$/);
    await page.getByRole("button",{name:"创建 JSONL 导出"}).click();
    await page.getByRole("button",{name:"确认导出"}).click();
    await expect(page.getByText(/提交时范围.*00:00:10.*00:00:12/)).toBeVisible();
    expect(submitted).toHaveLength(2);
    expect(submitted[1]).toContain('"format":"jsonl"');
    const downloadPromise=page.waitForEvent("download");
    await page.getByRole("button",{name:"下载已验证的 JSONL"}).click();
    const download=await downloadPromise;
    expect(download.suggestedFilename()).toBe("e2.jsonl");
    const stream=await download.createReadStream();
    const downloaded=stream===null?"":(await readStream(stream)).toString("utf-8");
    expect(downloaded).toBe(files.get("e2"));
    expect(createHash("sha256").update(downloaded).digest("hex")).toBe(artifacts.get("e2")?.sha256);
  });
});

function readStream(stream:NodeJS.ReadableStream):Promise<Buffer>{
  return new Promise((resolve,reject)=>{
    const chunks:Buffer[]=[];
    stream.on("data",(chunk:Buffer)=>chunks.push(chunk));
    stream.on("end",()=>resolve(Buffer.concat(chunks)));
    stream.on("error",reject);
  });
}
