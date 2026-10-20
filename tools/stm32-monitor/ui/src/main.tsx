import {createStartupSession,renderStartupError} from "./bootstrap";
import "./styles.css";

const startup=createStartupSession(window,fetch);
let inFlight=false;
let mounted=false;
async function checkStartup():Promise<void>{
  if(inFlight||mounted)return;
  inFlight=true;
  try{
    const result=await startup.check();
    if(!result.ok){
      renderStartupError(document,result.code,
        startup.canRecheckSession&&result.code==="MONITOR_SESSION_EXPIRED"?checkStartup:undefined);
      return;
    }
    const [{render,h},{App}]=await Promise.all([import("preact"),import("./app")]);
    mounted=true;
    render(h(App,{}),document.getElementById("app")!);
  }finally{
    inFlight=false;
  }
}
await checkStartup();
