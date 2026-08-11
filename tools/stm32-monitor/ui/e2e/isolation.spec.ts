import {expect,test} from "@playwright/test";
import {startMonitor} from "./conftest";

test.describe("STM32 Monitor workspace isolation",()=>{
  let monitor:{url:string;accessUrl:string};

  test.beforeAll(async()=>{
    monitor=await startMonitor(process.cwd(),process.cwd());
  });

  test("a fresh workspace has no named preset groups",async({page})=>{
    await page.goto(monitor.accessUrl,{waitUntil:"domcontentloaded"});
    await expect(page.getByLabel("STM32 Monitor")).toBeAttached();
    await page.waitForTimeout(1500);
    await expect(page.getByText("Fake Project")).toBeVisible();
    const groupSection=page.getByLabel("Watch groups");
    await expect(groupSection).toBeVisible();
    // An empty workspace starts on a blank "New group" draft, not a named preset.
    await expect(groupSection.getByRole("heading",{name:"New group"})).toBeVisible();
  });

  test("group editing requires a name and a watch before create is enabled",async({page})=>{
    await page.goto(monitor.accessUrl,{waitUntil:"domcontentloaded"});
    await expect(page.getByLabel("STM32 Monitor")).toBeAttached();
    await page.waitForTimeout(1500);
    await page.getByRole("button",{name:"New group"}).click();
    const createButton=page.getByRole("button",{name:"Create group"});
    await expect(createButton).toBeDisabled();
    await page.getByLabel("Name").fill("Motor Watch");
    await expect(createButton).toBeDisabled();
  });
});
