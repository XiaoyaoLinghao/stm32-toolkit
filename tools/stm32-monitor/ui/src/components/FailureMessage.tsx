import type {JSX} from "preact";
import type {ApiFailure} from "../api/contract";
import {copy,failureText} from "../presentation/zh";

export function FailureMessage({failure,blocked=false}:{failure:ApiFailure;blocked?:boolean}):JSX.Element{
  const text=failureText(failure);
  return<div className="failure-message" role="alert">
    <strong>{text.title}</strong><p>{blocked?`${copy.blockedOperation}${copy.retryOpen}`:text.action}</p>
    <details><summary>{copy.diagnostics}</summary><code>{failure.code}</code><pre>{failure.message}</pre></details>
  </div>;
}
