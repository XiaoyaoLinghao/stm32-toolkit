import {useCallback,useLayoutEffect,useRef} from "preact/hooks";

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
    const visibleDialogs=[...document.querySelectorAll<HTMLElement>("[role='dialog']")]
      .filter(element=>!element.closest("[hidden]"));
    if(visibleDialogs[visibleDialogs.length-1]!==dialog)return;
    if(event.key==="Escape"){
      event.preventDefault();
      event.stopPropagation();
      onCancel();
      return;
    }
    if(event.key!=="Tab")return;
    event.stopPropagation();
    const focusable=[...dialog.querySelectorAll<HTMLElement>("a[href],button,input,select,textarea,[tabindex]:not([tabindex='-1'])")]
      .filter(element=>!element.hasAttribute("disabled")&&!element.closest("[hidden]")&&element.getAttribute("aria-hidden")!=="true");
    if(focusable.length===0){event.preventDefault();dialog.focus();return;}
    const first=focusable[0]!,last=focusable[focusable.length-1]!;
    if(event.shiftKey&&(document.activeElement===first||document.activeElement===dialog)){
      event.preventDefault();last.focus();
    }else if(!event.shiftKey&&(document.activeElement===last||document.activeElement===dialog)){
      event.preventDefault();first.focus();
    }
  },[onCancel]);
  return{rememberTrigger,dialogRef:setDialogRef,onDialogKeyDown};
}
