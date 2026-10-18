import type {JSX} from "preact";
import type {DropTotals} from "../state/model";
import {copy,latencyText} from "../presentation/zh";

export type StatusStripProps={
  actualRateHz:number;
  latencyNs:bigint;
  lastSampleCapturedAtUtc:string|null;
  fresh:boolean;
  drops:DropTotals;
  sourceLabel?:string;
  sourceFreshness?:string|undefined;
  compact?:boolean;
};

export function StatusStrip({actualRateHz,latencyNs,lastSampleCapturedAtUtc,fresh,drops,sourceLabel,sourceFreshness,compact=false}:StatusStripProps):JSX.Element{
  const hasDrops=Object.values(drops).some(value=>value>0n);
  const hasSample=lastSampleCapturedAtUtc!==null;
  const dropTotal=drops.subscriber+drops.history+drops.deadline+drops.service;
  return<section className={`status-strip ${compact?"compact":"detailed"} ${hasDrops?"has-drops":""}`} aria-label={copy.statusSummary} tabIndex={compact?0:undefined}>
    {!compact&&<h3>{copy.statusSummary}</h3>}
    {sourceLabel&&<span className="status-source" title={sourceLabel}>{copy.historySource} <output>{sourceLabel}</output></span>}
    {sourceFreshness&&<span className={fresh||!hasSample?"status-freshness":"status-freshness stale-label"}>{sourceFreshness}</span>}
    <span>{copy.actualRate} <output>{hasSample?`${actualRateHz.toFixed(2)} Hz`:copy.noSampleYet}</output></span>
    <span>{copy.latency} <output>{hasSample?latencyText(latencyNs):copy.noSampleYet}</output></span>
    {!compact&&hasSample&&<span>{copy.rawNs} <code>{latencyNs.toString()} ns</code></span>}
    {!compact&&hasSample&&<span className={fresh?"":"stale-label"}>{fresh?copy.historyCaptured:copy.lastSample}：<time>{lastSampleCapturedAtUtc}</time></span>}
    {compact?<span>{copy.dropTotal} <output>{dropTotal.toString()}</output></span>
      :<span>{copy.dropsSubscriber} <output>{drops.subscriber.toString()}</output> · {copy.dropsHistory} <output>{drops.history.toString()}</output> · {copy.dropsDeadline} <output>{drops.deadline.toString()}</output> · {copy.dropsService} <output>{drops.service.toString()}</output></span>}
  </section>;
}
