import type {JSX} from "preact";
import {useRef,useState} from "preact/hooks";
import type {MonitorState,OperationFailure,RequestScope} from "../state/model";
import {copy,errorText,recoveryAction,recoveryText} from "../presentation/zh";
import {useDialogFocus} from "./dialog-focus";

export function OperationRegion({failures,pending,reconciling,retryDisabledScopes=[],allowDismissInitial=true,onRetry,onDismiss}:{
  failures:MonitorState["failures"];pending:MonitorState["pending"];reconciling?:MonitorState["reconciling"];
  retryDisabledScopes?:readonly RequestScope[];
  allowDismissInitial?:boolean;
  onRetry:(scope:RequestScope,id:bigint)=>void|Promise<void>;
  onDismiss:(scope:RequestScope,id:bigint)=>void;
}):JSX.Element|null{
  const [confirm,setConfirm]=useState<{scope:RequestScope;id:bigint}|null>(null);
  const confirmRef=useRef<{scope:RequestScope;id:bigint}|null>(null);
  const clearConfirm=()=>{confirmRef.current=null;setConfirm(null);};
  const dialog=useDialogFocus(confirm!==null,clearConfirm);
  const entries:[RequestScope,OperationFailure][]=[];
  for(const scope of Object.keys(failures) as RequestScope[]){
    const failure=failures[scope];
    if(failure!==undefined)entries.push([scope,failure]);
  }
  if(entries.length===0)return null;
  const current=confirm===null?null:failures[confirm.scope]?.requestId===confirm.id?failures[confirm.scope]:null;
  return<section className="operation-region" aria-label={copy.operations}>
    <h2>{copy.operations}</h2>
    <ul>{entries.map(([scope,failure])=><li key={scope+String(failure.requestId)} role="alert">
      <div><strong>{failure.summary}</strong><p>{errorText(failure.code).title}。{recoveryText(failure.recovery,scope)}</p></div>
      <div className="operation-actions">
        {(failure.recovery==="read-retry"||failure.recovery==="write-confirm"||failure.recovery==="reconcile")&&
          <button type="button" disabled={pending[scope]!==undefined||reconciling?.[scope]===failure.requestId||retryDisabledScopes.includes(scope)} onClick={event=>{
            if(failure.recovery==="write-confirm"){dialog.rememberTrigger(event.currentTarget);const target={scope,id:failure.requestId};confirmRef.current=target;setConfirm(target);}
            else void onRetry(scope,failure.requestId);
          }}>{recoveryAction(failure.recovery,scope)}</button>}
        {(scope!=="initial"||allowDismissInitial)&&<button type="button" onClick={()=>{
          if(confirmRef.current?.scope===scope&&confirmRef.current.id===failure.requestId)clearConfirm();
          onDismiss(scope,failure.requestId);
        }}>{copy.close}</button>}
      </div>
      <details><summary>{copy.diagnostics}</summary><code>{failure.code}</code><pre>{failure.message}</pre></details>
    </li>)}</ul>
    {confirm!==null&&current!==null&&current!==undefined&&<div role="dialog" aria-modal="true" aria-label={copy.retryConfirm}
      tabIndex={-1} ref={dialog.dialogRef} onKeyDown={dialog.onDialogKeyDown}>
      <div><p>{copy.retryQuestion}</p><strong>{current.summary}</strong>
        <button type="button" disabled={pending[confirm.scope]!==undefined} onClick={()=>{
          if(confirmRef.current?.scope!==confirm.scope||confirmRef.current.id!==confirm.id)return;
          const latest=failures[confirm.scope];
          clearConfirm();
          if(latest?.requestId===confirm.id)void onRetry(confirm.scope,confirm.id);
        }}>{copy.retryConfirm}</button>
        <button type="button" onClick={clearConfirm}>{copy.cancel}</button>
      </div>
    </div>}
  </section>;
}
