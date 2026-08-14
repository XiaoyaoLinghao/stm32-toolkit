import {mkdirSync} from "node:fs";
import {isAbsolute,join,relative,resolve} from "node:path";
import AxeBuilder from "@axe-core/playwright";
import {expect,test,type Locator,type Page} from "@playwright/test";
import {installSameOriginGuard} from "./acceptance";
import {openMonitor,startMonitor} from "./conftest";

async function tabTo(page:Page,target:Locator):Promise<void>{
  for(let index=0;index<80;index+=1){
    await page.keyboard.press("Tab");
    if(await target.evaluate(element=>element===document.activeElement))return;
  }
  throw new Error("keyboard target was not reached");
}

test.describe("STM32 Monitor browser accessibility",()=>{
  let monitor:Awaited<ReturnType<typeof startMonitor>>;

  test.beforeEach(async()=>{
    monitor=await startMonitor(process.cwd(),process.env.STM32_MONITOR_EVIDENCE??process.cwd());
  });

  test.afterEach(async()=>{
    monitor.stop();
  });

  test("remains keyboard-operable and axe-clean at 200 percent zoom",async({page,context},testInfo)=>{
    const evidence=process.env.STM32_MONITOR_EVIDENCE;
    const evidencePath=evidence===undefined?"":resolve(evidence);
    const fromRepository=relative(resolve(process.cwd()),evidencePath);
    if(evidence===undefined||fromRepository===""||(!fromRepository.startsWith("..")&&!isAbsolute(fromRepository))){
      throw new Error("STM32_MONITOR_EVIDENCE must be a repository-external path");
    }
    const guard=await installSameOriginGuard(context,monitor.url);
    await page.emulateMedia({reducedMotion:"reduce"});
    await openMonitor(page,monitor.accessUrl);
    await page.evaluate(()=>{document.documentElement.style.zoom="200%";});

    expect([[1280,720],[1024,768]]).toContainEqual([
      page.viewportSize()?.width,
      page.viewportSize()?.height,
    ]);
    expect(await page.evaluate(()=>matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);

    const connect=page.getByRole("button",{name:"Connect",exact:true});
    await tabTo(page,connect);
    await expect(connect).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByText(/Connected: probe-a/)).toBeVisible();

    const name=page.getByLabel("Name",{exact:true});
    await tabTo(page,name);
    await page.keyboard.type("Keyboard group");
    const search=page.getByLabel("Search",{exact:true});
    await tabTo(page,search);
    await page.keyboard.type("counter");
    const add=page.getByRole("button",{name:"Add to group",exact:true});
    await tabTo(page,add);
    await page.keyboard.press("Enter");
    const create=page.getByRole("button",{name:"Create group",exact:true});
    await tabTo(page,create);
    await expect(create).toBeEnabled();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button",{name:"Keyboard group (1)"})).toBeVisible();
    const start=page.getByRole("button",{name:"Start",exact:true});
    await tabTo(page,start);
    await expect(start).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByText("RUNNING",{exact:true})).toBeVisible();

    // @axe-core/playwright currently carries a structurally newer Playwright
    // Page declaration than the release-pinned runner. Runtime compatibility
    // is covered by this real-browser test.
    const results=await new AxeBuilder({page:page as never}).analyze();
    expect(results.violations).toEqual([]);
    expect(guard.attempts).toEqual([]);

    const screenshotRoot=join(evidencePath,"screenshots");
    mkdirSync(screenshotRoot,{recursive:true});
    await page.screenshot({
      path:join(screenshotRoot,`accessibility-${testInfo.project.name}.png`),
      fullPage:true,
    });
  });
});
