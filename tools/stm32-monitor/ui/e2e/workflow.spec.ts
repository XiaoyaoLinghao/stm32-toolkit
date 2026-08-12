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
    await expect(page.getByLabel("STM32 Monitor")).toBeAttached();
    await expect(page.getByText("Fake Project")).toBeVisible();
  }

  async function connectProbe(page:import("@playwright/test").Page){
    await page.getByRole("button",{name:"Connect",exact:true}).click();
    await expect(page.getByText(/Connected: probe-a/)).toBeVisible();
  }

  async function addWatch(page:import("@playwright/test").Page,expression:string){
    await page.getByLabel("Search").fill(expression);
    await expect(page.getByRole("button",{name:"Add to group"})).toBeVisible();
    await page.getByRole("button",{name:"Add to group"}).click();
  }

  async function createGroup(page:import("@playwright/test").Page,name:string,expression:string){
    await page.getByRole("button",{name:"New group"}).click();
    await addWatch(page,expression);
    await page.getByLabel("Name").fill(name);
    const create=page.getByRole("button",{name:"Create group"});
    await expect(create).toBeEnabled();
    await create.click();
    await expect(page.getByRole("button",{name:`${name} (1)`})).toBeVisible();
  }

  test("fresh workspace starts with zero named groups",async({page})=>{
    await freshPage(page);
    const section=page.getByLabel("Watch groups");
    await expect(section.getByRole("heading",{name:"New group"})).toBeVisible();
    await expect(section.getByRole("button",{name:"Create group"})).toBeDisabled();
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
    await page.getByLabel("Name").fill("Renamed Watch");
    await page.getByRole("button",{name:"Save group"}).click();
    await expect(page.getByRole("button",{name:"Renamed Watch (1)"})).toBeVisible();
  });

  test("deletes a group only after explicit confirmation",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await createGroup(page,"Motor Watch","counter");
    await page.getByRole("button",{name:"Delete"}).click();
    await expect(page.getByRole("button",{name:"Confirm delete"})).toBeVisible();
    await page.getByRole("button",{name:"Cancel"}).click();
    await expect(page.getByRole("button",{name:"Motor Watch (1)"})).toBeVisible();
    await page.getByRole("button",{name:"Delete"}).click();
    await page.getByRole("button",{name:"Confirm delete"}).click();
    await expect(page.getByRole("button",{name:"Motor Watch (1)"})).not.toBeVisible();
  });

  test("imports a group document after preview and second confirmation",async({page})=>{
    await freshPage(page);
    await page.getByRole("button",{name:"Import groups"}).click();
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
    await expect(page.getByText(/Import 1 groups/)).toBeVisible();
    await page.getByRole("button",{name:"Confirm import"}).click();
    await expect(page.getByRole("button",{name:"Imported (0)"})).toBeVisible();
  });

  test("rejects an invalid import without sending it",async({page})=>{
    await freshPage(page);
    await page.getByRole("button",{name:"Import groups"}).click();
    await page.getByTestId("group-import-file").setInputFiles({
      name:"bad.json",
      mimeType:"application/json",
      buffer:Buffer.from('{"schemaVersion":1,"groups":{}}'),
    });
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button",{name:"Confirm import"})).not.toBeVisible();
  });

  test("exports authoritative groups as a blob download",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await createGroup(page,"Motor Watch","counter");
    const downloadPromise=page.waitForEvent("download");
    await page.getByRole("button",{name:"Export groups JSON"}).click();
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
    const state=page.getByLabel("Sampling controls").getByRole("status");
    await page.getByRole("button",{name:"Start"}).click();
    await expect(state).toContainText("RUNNING");
    await page.getByRole("button",{name:"Pause"}).click();
    await expect(state).toContainText("PAUSED");
    await page.getByRole("button",{name:"Resume"}).click();
    await expect(state).toContainText("RUNNING");
    await page.getByRole("button",{name:"Stop"}).click();
    await expect(state).toContainText("IDLE");
  });

  test("one failed item does not block the live table value",async({page})=>{
    await freshPage(page);
    await connectProbe(page);
    await page.getByRole("button",{name:"New group"}).click();
    await addWatch(page,"counter");
    await addWatch(page,"faulty");
    await page.getByLabel("Name").fill("Motor Watch");
    await page.getByRole("button",{name:"Create group"}).click();
    await page.getByRole("button",{name:"Start"}).click();
    await expect(page.getByLabel("Sampling controls").getByRole("status")).toContainText("RUNNING");
    const table=page.getByRole("region",{name:"Live values"}).getByRole("table");
    await expect(table).toContainText("counter");
    await expect(table).toContainText("MONITOR_SAMPLE_ITEM_FAILED");
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
