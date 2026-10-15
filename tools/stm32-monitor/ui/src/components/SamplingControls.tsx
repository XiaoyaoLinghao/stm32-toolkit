import type {JSX} from "preact";
import type {ApiFailure,SamplingStatus} from "../api/contract";
import type {WatchGroup} from "../api/contract";
import {copy,samplingState} from "../presentation/zh";
import {FailureMessage} from "./FailureMessage";

export type SamplingControlsProps={
  status:SamplingStatus;
  group:WatchGroup|null;
  onStart:(groupId:string,expectedRevision:bigint)=>void|Promise<void>;
  onPause:()=>void|Promise<void>;
  onResume:()=>void|Promise<void>;
  onStop:()=>void|Promise<void>;
  failure:ApiFailure|null;
  busy?:boolean;
};

export function SamplingControls(p:SamplingControlsProps):JSX.Element{
  const state=p.status.state;
  const canStart=state==="IDLE"||state==="STOPPING";
  return<section className="panel sampling-controls" aria-label={copy.samplingControls}>
    <div className="sampling-heading"><h2>{copy.samplingTitle}</h2><p role="status" aria-live="polite">{samplingState(state)}{p.status.blockedCode!==null?copy.samplingBlocked:""}</p></div>
    <p>{copy.samplingGroup}{p.group===null?copy.samplingNoGroup:p.group.name}</p>
    <button type="button" disabled={p.group===null||!canStart||p.busy}
      onClick={()=>{if(p.group!==null)void p.onStart(p.group.groupId,p.group.revision);}}>
      {copy.samplingStart}
    </button>
    <button type="button" disabled={state!=="RUNNING"||p.busy}
      onClick={()=>void p.onPause()}>{copy.samplingPause}</button>
    <button type="button" disabled={state!=="PAUSED"&&state!=="PAUSED_BLOCKED"||p.busy}
      onClick={()=>void p.onResume()}>{copy.samplingResume}</button>
    <button type="button" disabled={!p.status.active&&state==="IDLE"||p.busy}
      onClick={()=>void p.onStop()}>{copy.samplingStop}</button>
    {p.status.blockedCode!==null&&<details><summary>{copy.diagnostics}</summary><code>{p.status.blockedCode}</code></details>}
    {p.failure!==null&&<FailureMessage failure={p.failure}/>}
  </section>;
}
