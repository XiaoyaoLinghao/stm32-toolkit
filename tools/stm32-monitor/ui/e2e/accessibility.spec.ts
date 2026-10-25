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

    await page.getByRole("button",{name:"连接与固件详情"}).click();
    const connect=page.getByRole("button",{name:"连接",exact:true});
    await tabTo(page,connect);
    await expect(connect).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("status",{name:"探针操作结果"})).toContainText("探针连接成功");
    await page.getByRole("button",{name:"连接与固件详情"}).click();
    await expect(page.getByText(/已连接：probe-a/)).toBeVisible();
    await page.getByRole("button",{name:"关闭设备详情",exact:true}).click();

    // The group editor is a modal drawer; its draft survives closing it while
    // the source catalog in the sidebar is used to add the watch.
    await page.getByRole("button",{name:"编辑并保存",exact:true}).click();
    await page.getByRole("button",{name:"新建观测组"}).click();
    const name=page.getByLabel("名称",{exact:true});
    await tabTo(page,name);
    await page.keyboard.type("Keyboard group");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog",{name:"观测组"})).toBeHidden();
    await page.getByRole("tab",{name:"源码目录",exact:true}).click();
    const search=page.getByLabel("搜索",{exact:true});
    await tabTo(page,search);
    await page.keyboard.type("counter");
    await page.keyboard.press("Enter");
    const file=page.getByRole("button",{name:"展开 firmware/main.c",exact:true});
    await expect(file).toBeVisible();
    await tabTo(page,file);
    await page.keyboard.press("Enter");
    const add=page.getByRole("button",{name:"加入观测组草稿 counter",exact:true});
    await expect(add).toBeVisible();
    await tabTo(page,add);
    await page.keyboard.press("Enter");
    await expect(page.getByText("已加入组草稿（尚未保存）",{exact:true})).toBeVisible();
    const editor=page.getByRole("button",{name:"编辑并保存",exact:true});
    await tabTo(page,editor);
    await page.keyboard.press("Enter");
    const create=page.getByRole("button",{name:"创建观测组",exact:true});
    await tabTo(page,create);
    await expect(create).toBeEnabled();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button",{name:"Keyboard group (1)"})).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog",{name:"观测组"})).toBeHidden();
    const start=page.getByRole("button",{name:"开始采样",exact:true});
    await tabTo(page,start);
    await expect(start).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByText("采样中",{exact:true}).first()).toBeVisible();

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
