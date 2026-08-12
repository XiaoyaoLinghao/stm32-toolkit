import type {JSX} from "preact";
import type {ApiFailure,SamplingStatus} from "../api/contract";
import type {WatchGroup} from "../api/contract";

export type SamplingControlsProps={
  status:SamplingStatus;
  group:WatchGroup|null;
  onStart:(groupId:string,expectedRevision:bigint)=>void|Promise<void>;
  onPause:()=>void|Promise<void>;
  onResume:()=>void|Promise<void>;
  onStop:()=>void|Promise<void>;
  failure:ApiFailure|null;
};

export function SamplingControls(p:SamplingControlsProps):JSX.Element{
  const state=p.status.state;
  const canStart=state==="IDLE"||state==="STOPPING";
  return<section className="panel" aria-label="Sampling controls">
    <h2>Sampling</h2>
    <p>State: <output>{state}</output> · Group: {p.group===null?"none":p.group.name}</p>
    <button type="button" disabled={p.group===null||!canStart}
      onClick={()=>{if(p.group!==null)void p.onStart(p.group.groupId,p.group.revision);}}>
      Start
    </button>
    <button type="button" disabled={state!=="RUNNING"}
      onClick={()=>void p.onPause()}>Pause</button>
    <button type="button" disabled={state!=="PAUSED"&&state!=="PAUSED_BLOCKED"}
      onClick={()=>void p.onResume()}>Resume</button>
    <button type="button" disabled={!p.status.active&&state==="IDLE"}
      onClick={()=>void p.onStop()}>Stop</button>
    {p.failure!==null&&<p role="alert">{p.failure.code}: {p.failure.message}</p>}
  </section>;
}
