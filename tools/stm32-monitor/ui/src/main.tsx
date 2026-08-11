import {bootstrapFromFragment,renderStartupError} from "./bootstrap";
import "./styles.css";
const result=await bootstrapFromFragment(window,fetch);
if(!result.ok){
  renderStartupError(document);
}else{
  const [{render,h},{App}]=await Promise.all([import("preact"),import("./app")]);
  render(h(App,{}),document.getElementById("app")!);
}
