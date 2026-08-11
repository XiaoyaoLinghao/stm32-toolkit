import {expect,test} from "@playwright/test";
import {openMonitor,startMonitor} from "./conftest";

test.describe("STM32 Monitor end-to-end",()=>{
  let monitor:{url:string;accessUrl:string};

  test.beforeAll(async()=>{
    monitor=await startMonitor(process.cwd(),process.env.STM32_MONITOR_EVIDENCE??process.cwd());
  });

  test("serves the bundled UI at the root",async({page})=>{
    await page.goto(monitor.url,{waitUntil:"domcontentloaded"});
    await expect(page.locator("#app")).toBeAttached();
  });

  test("bootstraps from a fragment token and renders the shell",async({page})=>{
    await openMonitor(page,monitor.accessUrl);
    await expect(page.getByLabel("STM32 Monitor")).toBeAttached();
    await expect(page.getByText("Fake Project")).toBeVisible();
  });

  test("serves content-hashed assets with immutable caching",async({page,request})=>{
    await page.goto(monitor.url,{waitUntil:"domcontentloaded"});
    const html=await page.content();
    const scriptMatch=/src="(\/assets\/[^"]+)"/.exec(html);
    expect(scriptMatch).not.toBeNull();
    if(scriptMatch===null)return;
    const response=await request.get(`${monitor.url}${scriptMatch[1]}`);
    expect(response.status()).toBe(200);
    expect(response.headers()["cache-control"]).toContain("immutable");
    expect(response.headers()["etag"]).toBeTruthy();
    expect(response.headers()["x-content-type-options"]).toBe("nosniff");
    expect(response.headers()["content-security-policy"]).toContain("connect-src 'self'");
  });

  test("rejects unknown asset routes",async({request})=>{
    const response=await request.get(`${monitor.url}/assets/nope-NotAHash.js`);
    expect(response.status()).toBe(404);
  });

  test("does not fall back from API routes to the SPA",async({request})=>{
    const response=await request.get(`${monitor.url}/api/v1/status`);
    expect(response.status()).toBe(401);
  });

  test("bootstraps with Bearer and then uses the HttpOnly cookie",async({page,context})=>{
    const tokenRequest=page.waitForRequest(
      request=>request.url().includes("/api/v1/auth/bootstrap")
    );
    await page.goto(monitor.accessUrl,{waitUntil:"domcontentloaded"});
    const request=await tokenRequest;
    expect(request.headers()["authorization"]??"").toMatch(/^Bearer [0-9a-f]{64}$/);
    expect(request.headers()["origin"]).toBeUndefined();
    const cookies=await context.cookies();
    const monitorCookie=cookies.find(cookie=>cookie.name==="stm32_monitor_session");
    expect(monitorCookie).toBeDefined();
    if(monitorCookie!==undefined){
      expect(monitorCookie.httpOnly).toBe(true);
      expect(monitorCookie.sameSite).toBe("Strict");
    }
    expect(page.url()).not.toContain("token=");
  });
});
