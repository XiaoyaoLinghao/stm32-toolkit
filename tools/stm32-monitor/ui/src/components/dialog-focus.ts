import {useCallback,useRef} from "preact/hooks";

export function useDialogFocus(open:boolean,onCancel:()=>void):{
  rememberTrigger:(element:HTMLElement)=>void;
  dialogRef:(element:HTMLElement|null)=>void;
  onDialogKeyDown:(event:KeyboardEvent)=>void;
}{
  const triggerRef=useRef<HTMLElement|null>(null);
  const dialogRef=useRef<HTMLElement|null>(null);
  const rememberTrigger=useCallback((element:HTMLElement)=>{triggerRef.current=element;},[]);
  const setDialogRef=useCallback((element:HTMLElement|null)=>{dialogRef.current=element;if(element!==null)element.focus();},[]);
  const onDialogKeyDown=useCallback((event:KeyboardEvent)=>{
    if(event.key==="Escape"){onCancel();triggerRef.current?.focus();}
  },[onCancel]);
  return{rememberTrigger,dialogRef:setDialogRef,onDialogKeyDown};
}
