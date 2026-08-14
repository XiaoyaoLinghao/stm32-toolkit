import {createServer} from "node:http";
import {once} from "node:events";
import {expect,test} from "@playwright/test";
import {installSameOriginGuard} from "./acceptance";
import {fixtureToken,openMonitor,startMonitor} from "./conftest";

async function startSentinel():Promise<{origin:string;requests:()=>number;stop:()=>Promise<void>}>{
  let requestCount=0;
  const server=createServer((_request,response)=>{
    requestCount+=1;
    response.writeHead(204).end();
  });
  server.listen(0,"127.0.0.1");
  await once(server,"listening");
  const address=server.address();
  if(address===null||typeof address==="string")throw new Error("sentinel did not bind TCP");
  return{
    origin:`http://127.0.0.1:${address.port}`,
    requests:()=>requestCount,
    stop:async()=>{
      server.closeAllConnections();
      server.close();
    },
  };
}

test.describe("STM32 Monitor browser security",()=>{
  let monitor:Awaited<ReturnType<typeof startMonitor>>;

  test.beforeEach(async()=>{
    monitor=await startMonitor(process.cwd(),process.env.STM32_MONITOR_EVIDENCE??process.cwd());
  });

  test.afterEach(async()=>{
    monitor.stop();
  });

  test("keeps the bootstrap secret out of browser-visible surfaces and stays same-origin",async({page,context})=>{
    const token=fixtureToken(monitor.accessUrl);
    const consoleMessages:string[]=[];
    page.on("console",message=>consoleMessages.push(message.text()));
    const guard=await installSameOriginGuard(context,monitor.url);

    await openMonitor(page,monitor.accessUrl);

    const browserSurfaces=await page.evaluate(async()=>JSON.stringify({
      url:location.href,
      html:document.documentElement.outerHTML,
      attributes:[...document.querySelectorAll("*")].flatMap(element=>
        [...element.attributes].map(attribute=>[attribute.name,attribute.value])),
      inputs:[...document.querySelectorAll("input,textarea,select")].map(element=>(
        element instanceof HTMLInputElement||element instanceof HTMLTextAreaElement
          ?element.value
          :element instanceof HTMLSelectElement?element.value:""
      )),
      local:Object.entries(localStorage),
      session:Object.entries(sessionStorage),
      databases:(await indexedDB.databases()).map(database=>database.name??""),
      cookie:document.cookie,
    }));
    expect(browserSurfaces).not.toContain(token);
    expect(consoleMessages.join("\n")).not.toContain(token);
    expect(page.url()).toBe(`${monitor.url}/`);
    expect(guard.attempts).toEqual([]);

    const response=await page.request.get(`${monitor.url}/`);
    expect(response.status()).toBe(200);
    const headers=response.headers();
    const port=new URL(monitor.url).port;
    expect(headers["cache-control"]).toBe("no-store");
    expect(headers["referrer-policy"]).toBe("no-referrer");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["cross-origin-opener-policy"]).toBe("same-origin");
    expect(headers["cross-origin-resource-policy"]).toBe("same-origin");
    expect(headers["permissions-policy"]).toBe(
      "camera=(), microphone=(), geolocation=(), usb=(), serial=(), payment=()",
    );
    expect(headers["content-security-policy"]).toBe(
      "default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "+
      "form-action 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "+
      `font-src 'self'; connect-src 'self' ws://127.0.0.1:${port}; worker-src 'none'; `+
      "child-src 'none'; media-src 'none'",
    );

    const resourceOrigins=await page.evaluate(()=>(
      performance.getEntriesByType("resource")
        .map(entry=>new URL(entry.name).origin)
        .filter((origin,index,values)=>values.indexOf(origin)===index)
    ));
    expect(resourceOrigins).toEqual([monitor.url]);
  });

  test("blocks a non-current origin before the browser can send it",async({page,context})=>{
    const sentinel=await startSentinel();
    try{
      const guard=await installSameOriginGuard(context,monitor.url);
      await openMonitor(page,monitor.accessUrl);
      await page.goto(`${sentinel.origin}/must-not-leave-the-browser`,{
        waitUntil:"commit",
        timeout:3_000,
      }).catch(()=>undefined);

      expect(guard.attempts).toContain(sentinel.origin);
      expect(sentinel.requests()).toBe(0);
    }finally{
      await sentinel.stop();
    }
  });
});
