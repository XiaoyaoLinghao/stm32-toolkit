import {Buffer} from "node:buffer";
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
    await expect(page.getByText("Fake Project")).toBeVisible();
  }

  async function connectProbe(page:import("@playwright/test").Page){
    await page.getByRole("button",{name:"连接与固件详情"}).click();
    await page.getByRole("button",{name:"连接",exact:true}).click();
    await expect(page.getByText(/已连接：probe-a/)).toBeVisible();
    await page.getByRole("button",{name:"关闭"}).click();
  }

  async function addWatch(page:import("@playwright/test").Page,expression:string){
    const catalog=page.getByRole("button",{name:"浏览变量与寄存器"});
    if(await catalog.isVisible())await catalog.click();
    await page.getByLabel("搜索").fill(expression);
    await expect(page.getByRole("button",{name:"加入观测组草稿"})).toBeVisible();
    await page.getByRole("button",{name:"加入观测组草稿"}).click();
  }

  async function createGroup(page:import("@playwright/test").Page,name:string,expression:string){
    await page.getByRole("button",{name:"新建观测组"}).click();
    await addWatch(page,expression);
    await page.getByLabel("名称").fill(name);
    const create=page.getByRole("button",{name:"创建观测组"});
    await expect(create).toBeEnabled();
    await create.click();
    await expect(page.getByRole("button",{name:`${name} (1)`})).toBeVisible();
  }

  test("fresh workspace starts with zero named groups",async({page})=>{
    await freshPage(page);
    const section=page.getByLabel("观测组");
    await section.getByRole("button",{name:"新建观测组"}).click();
    await expect(section.getByRole("heading",{name:"新建观测组草稿"})).toBeVisible();
    await expect(section.getByRole("button",{name:"创建观测组"})).toBeDisabled();
  });

  test("creates a group from the blank draft",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await createGroup(page,"Motor Watch","counter");
    await expect(page.getByText("Motor Watch (1)")).toBeVisible();
  });

  test("edits an existing group via expected revision save",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await createGroup(page,"Motor Watch","counter");
    await page.getByLabel("名称").fill("Renamed Watch");
    await page.getByRole("button",{name:"保存观测组"}).click();
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
    await page.getByRole("button",{name:"新建观测组"}).click();
    await addWatch(page,"counter");
    await addWatch(page,"faulty");
    await page.getByLabel("名称").fill("Motor Watch");
    await page.getByRole("button",{name:"创建观测组"}).click();
    await page.getByRole("button",{name:"开始采样"}).click();
    await expect(page.getByLabel("采样控制").getByRole("status")).toContainText("采样中");
    const table=page.getByRole("region",{name:"最新数值"}).getByRole("table");
    await expect(table).toContainText("counter");
    await expect(table).toContainText("读取失败");
    await expect(table).toContainText("faulty");
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
