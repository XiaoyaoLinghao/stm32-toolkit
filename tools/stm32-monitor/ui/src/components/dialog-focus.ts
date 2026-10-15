import {useCallback,useLayoutEffect,useRef} from "preact/hooks";

export function useDialogFocus(open:boolean,onCancel:()=>void):{
  rememberTrigger:(element:HTMLElement)=>void;
  dialogRef:(element:HTMLElement|null)=>void;
  onDialogKeyDown:(event:KeyboardEvent)=>void;
}{
  const triggerRef=useRef<HTMLElement|null>(null);
  const dialogRef=useRef<HTMLElement|null>(null);
  const wasOpenRef=useRef(open);
  const rememberTrigger=useCallback((element:HTMLElement)=>{triggerRef.current=element;},[]);
  const setDialogRef=useCallback((element:HTMLElement|null)=>{dialogRef.current=element;if(element!==null)element.focus();},[]);
  useLayoutEffect(()=>{
    if(wasOpenRef.current&&!open){
      const trigger=triggerRef.current;
      const available=(element:HTMLElement):boolean=>element.isConnected&&!element.hasAttribute("disabled")&&!element.closest("[hidden]");
      if(trigger!==null){
        const fallback=[...(trigger.closest("section")??document).querySelectorAll<HTMLElement>("button,input,select,textarea,a[href],[tabindex]:not([tabindex='-1'])")]
          .find(element=>element!==trigger&&available(element));
        (available(trigger)?trigger:fallback)?.focus();
      }
    }
    wasOpenRef.current=open;
  },[open]);
  const onDialogKeyDown=useCallback((event:KeyboardEvent)=>{
    if(event.key==="Escape"){
      event.preventDefault();
      onCancel();
      return;
    }
    if(event.key!=="Tab")return;
    const dialog=dialogRef.current;
    if(dialog===null)return;
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
