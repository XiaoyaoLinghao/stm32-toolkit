import {expect,test} from "@playwright/test";
import {startMonitor} from "./conftest";

test.describe("STM32 Monitor workspace isolation",()=>{
  let monitor:{url:string;accessUrl:string};

  test.beforeAll(async()=>{
    monitor=await startMonitor(process.cwd(),process.cwd());
  });

  test("a fresh workspace has no named preset groups",async({page})=>{
    await page.goto(monitor.accessUrl,{waitUntil:"domcontentloaded"});
    await expect(page.getByLabel("STM32 监视器")).toBeAttached();
    await page.waitForTimeout(1500);
    await expect(page.getByText("Fake Project")).toBeVisible();
    const groupSection=page.getByLabel("观测组");
    await expect(groupSection).toBeVisible();
    // An empty workspace has no named preset and allows a blank draft.
    await groupSection.getByRole("button",{name:"新建观测组"}).click();
    await expect(groupSection.getByRole("heading",{name:"新建观测组草稿"})).toBeVisible();
  });

  test("group editing requires a name and a watch before create is enabled",async({page})=>{
    await page.goto(monitor.accessUrl,{waitUntil:"domcontentloaded"});
    await expect(page.getByLabel("STM32 监视器")).toBeAttached();
    await page.waitForTimeout(1500);
    await page.getByRole("button",{name:"新建观测组"}).click();
    const createButton=page.getByRole("button",{name:"创建观测组"});
    await expect(createButton).toBeDisabled();
    await page.getByLabel("名称").fill("Motor Watch");
    await expect(createButton).toBeDisabled();
  });
});
