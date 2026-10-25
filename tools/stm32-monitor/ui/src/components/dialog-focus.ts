import {useCallback,useEffect,useLayoutEffect,useRef} from "preact/hooks";

const focusableSelector="a[href],button,input,select,textarea,[tabindex]:not([tabindex='-1'])";
const visibleTopmost=(dialog:HTMLElement):boolean=>{
  if(!dialog.isConnected||dialog.closest("[hidden]")!==null)return false;
  const visible=[...document.querySelectorAll<HTMLElement>("[role='dialog']")]
    .filter(element=>!element.closest("[hidden]"));
  return visible[visible.length-1]===dialog;
};
const focusableIn=(dialog:HTMLElement):HTMLElement[]=>[...dialog.querySelectorAll<HTMLElement>(focusableSelector)]
  .filter(element=>!element.hasAttribute("disabled")&&!element.closest("[hidden]")&&element.getAttribute("aria-hidden")!=="true");

export function useDialogFocus(open:boolean,onCancel:()=>void,fallbackTrigger?:()=>HTMLElement|null):{
  rememberTrigger:(element:HTMLElement)=>void;
  dialogRef:(element:HTMLElement|null)=>void;
  onDialogKeyDown:(event:KeyboardEvent)=>void;
}{
  const triggerRef=useRef<HTMLElement|null>(null);
  const fallbackRef=useRef(fallbackTrigger);
  fallbackRef.current=fallbackTrigger;
  const dialogRef=useRef<HTMLElement|null>(null);
  const wasOpenRef=useRef(open);
  const cancelRef=useRef(onCancel);cancelRef.current=onCancel;
  const rememberTrigger=useCallback((element:HTMLElement)=>{triggerRef.current=element;},[]);
  const focusDialog=useCallback((element:HTMLElement)=>{
    if(element.closest("[hidden]"))return;
    (element.querySelector<HTMLElement>("[role='dialog']:not([hidden])")??element).focus();
  },[]);
  const setDialogRef=useCallback((element:HTMLElement|null)=>{dialogRef.current=element;if(element!==null&&open)focusDialog(element);},[open,focusDialog]);
  useLayoutEffect(()=>{
    if(open&&!wasOpenRef.current&&dialogRef.current!==null)focusDialog(dialogRef.current);
    if(wasOpenRef.current&&!open){
      const trigger=triggerRef.current;
      const available=(element:HTMLElement):boolean=>element.isConnected&&!element.hasAttribute("disabled")&&!element.closest("[hidden]");
      if(trigger!==null){
        const selector="button,input,select,textarea,a[href],[tabindex]:not([tabindex='-1'])";
        const preferred=fallbackRef.current?.();
        const fallback=(preferred!==undefined&&preferred!==null&&available(preferred)?preferred:undefined)??[...(trigger.closest("section")??document).querySelectorAll<HTMLElement>(selector)]
          .find(element=>element!==trigger&&available(element))??[...document.querySelectorAll<HTMLElement>(selector)]
          .find(element=>element!==trigger&&available(element));
        (available(trigger)?trigger:fallback)?.focus();
      }
    }
    wasOpenRef.current=open;
  },[open,focusDialog]);
  const onDialogKeyDown=useCallback((event:KeyboardEvent)=>{
    const dialog=dialogRef.current;
    if(dialog===null||event.defaultPrevented)return;
    if(!visibleTopmost(dialog))return;
    if(event.key==="Escape"){
      event.preventDefault();
      event.stopPropagation();
      cancelRef.current();
      return;
    }
    if(event.key!=="Tab")return;
    event.stopPropagation();
    const focusable=focusableIn(dialog);
    if(focusable.length===0){event.preventDefault();dialog.focus();return;}
    const first=focusable[0]!,last=focusable[focusable.length-1]!;
    if(event.shiftKey&&(document.activeElement===first||document.activeElement===dialog)){
      event.preventDefault();last.focus();
    }else if(!event.shiftKey&&(document.activeElement===last||document.activeElement===dialog)){
      event.preventDefault();first.focus();
    }
  },[]);
  // A modal can lose its focused control when a write disables or removes it.
  // Recover focus into the topmost visible dialog and keep Escape/Tab working
  // even when the key event no longer passes through the dialog element. These
  // document listeners run in the bubble phase and honour defaultPrevented, so
  // a child that deliberately consumes the key keeps its behaviour.
  useEffect(()=>{
    if(!open)return;
    const inside=(dialog:HTMLElement,value:EventTarget|null):boolean=>value instanceof Node&&dialog.contains(value);
    const activeDialog=():HTMLElement|null=>{
      const dialog=dialogRef.current;
      return dialog!==null&&visibleTopmost(dialog)?dialog:null;
    };
    const recover=()=>{
      const dialog=activeDialog();if(dialog===null)return;
      const active=document.activeElement;
      if(active instanceof HTMLElement&&active.isConnected&&dialog.contains(active)&&!active.hasAttribute("disabled"))return;
      focusDialog(dialog);
    };
    const onFocusIn=(event:FocusEvent)=>{
      const dialog=activeDialog();
      if(dialog===null||inside(dialog,event.target))return;
      focusDialog(dialog);
    };
    const onFocusOut=(event:FocusEvent)=>{
      const dialog=activeDialog();
      if(dialog===null||!inside(dialog,event.target)||event.relatedTarget!==null)return;
      focusDialog(dialog);
    };
    const onKeyDown=(event:KeyboardEvent)=>{
      const dialog=activeDialog();
      if(dialog===null||event.defaultPrevented||inside(dialog,event.target))return;
      if(event.key==="Escape"){
        event.preventDefault();
        event.stopPropagation();
        cancelRef.current();
        return;
      }
      if(event.key!=="Tab")return;
      event.preventDefault();
      const focusable=focusableIn(dialog);
      if(focusable.length===0){dialog.focus();return;}
      (event.shiftKey?focusable[focusable.length-1]:focusable[0])!.focus();
    };
    document.addEventListener("focusin",onFocusIn);
    document.addEventListener("focusout",onFocusOut);
    document.addEventListener("keydown",onKeyDown);
    const dialog=dialogRef.current;
    const observer=dialog===null?null:new MutationObserver(recover);
    if(dialog!==null)observer?.observe(dialog,{subtree:true,childList:true,attributes:true,attributeFilter:["disabled","hidden"]});
    return()=>{
      document.removeEventListener("focusin",onFocusIn);
      document.removeEventListener("focusout",onFocusOut);
      document.removeEventListener("keydown",onKeyDown);
      observer?.disconnect();
    };
  },[open,focusDialog]);
  return{rememberTrigger,dialogRef:setDialogRef,onDialogKeyDown};
}
