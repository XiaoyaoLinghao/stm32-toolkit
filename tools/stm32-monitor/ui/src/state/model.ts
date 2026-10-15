import type {ApiFailure,ExportArtifact,GroupDraft,HistoryPage,HistoryQuery,MonitorStatus,ObservationBinding,ProbeInfo,SampleValue,VariableDescriptor,RegisterDescriptor,WatchGroup,WatchItem} from "../api/contract";
import type {ChartPoint,LiveRow} from "../chart/series";
import type {ZoomRange} from "../chart/zoom";

export type DropTotals={subscriber:bigint;history:bigint;deadline:bigint;service:bigint};
export type RequestScope="initial"|"status"|"probes"|"probe.connect"|"probe.reconnect"|"probe.release"|"catalog.variables"|"catalog.registers"|"groups.list"|"groups.create"|"groups.update"|"groups.delete"|"groups.import"|"sampling.start"|"sampling.pause"|"sampling.resume"|"sampling.stop"|"history"|"export.create"|"export.status"|"export.download";
export type PendingRequest={requestId:bigint};
export type RecoveryKind="read-retry"|"write-confirm"|"reconcile"|"input"|"none";
export type OperationFailure=ApiFailure&{requestId:bigint;recovery:RecoveryKind;summary:string};
export type CatalogKind="variables"|"registers";
export type VariableCatalog={kind:"variables";query:string;bindingKey:string;cursor:string|null;items:readonly VariableDescriptor[];nextCursor:string|null};
export type RegisterCatalog={kind:"registers";query:string;bindingKey:string;cursor:string|null;items:readonly RegisterDescriptor[];nextCursor:string|null};
export type HistoryRow={runId:string;sequence:bigint;startOrdinal:bigint;batchValueCount:bigint;capturedAtUtc:string;values:readonly SampleValue[]};
export type HistoryProjection={rows:readonly HistoryRow[];series:ReadonlyMap<string,readonly ChartPoint[]>};
export type DisplaySeries={key:string;label:string;points:readonly ChartPoint[]};
export type LiveState={rows:ReadonlyMap<string,LiveRow>;series:ReadonlyMap<string,readonly ChartPoint[]>;selectedSeries:ReadonlySet<string>;binding:ObservationBinding|null;bindingEpoch:bigint|null;runId:string|null;segment:bigint;lastSequence:bigint|null;actualRateHz:number;latencyNs:bigint;authoritativeDrops:DropTotals;pendingDropDeltas:DropTotals};
export type Notice={id:string;kind:"view-reset"|"drop";text:string};
export type MonitorState={status:MonitorStatus|null;probes:readonly ProbeInfo[];groups:readonly WatchGroup[];selectedGroupId:string|null;groupDraft:GroupDraft;stateRevision:bigint;lastAcceptedEventId:bigint|null;pending:Readonly<Partial<Record<RequestScope,PendingRequest>>>;reconciling:Readonly<Partial<Record<RequestScope,bigint>>>;failures:Readonly<Partial<Record<RequestScope,OperationFailure>>>;catalog:{variables:VariableCatalog|null;registers:RegisterCatalog|null};selectedSeries:ReadonlySet<string>;live:LiveState;zoom:ZoomRange;transport:{open:boolean;stale:boolean;needsStatusRefresh:boolean};history:{query:HistoryQuery|null;page:HistoryPage|null;projection:HistoryProjection;cursorIndex:number;cursorStack:readonly (string|undefined)[];nextCursor:string|null};exports:{artifact:ExportArtifact|null;submitted:{exportId:string;startNs:bigint;endNs:bigint;format:"csv"|"jsonl"}|null};notices:readonly Notice[];blockingError:ApiFailure|null};

export type LoadedAction=
 | {type:"initial.loaded";status:MonitorStatus;probes:readonly ProbeInfo[];groups:readonly WatchGroup[]}
 | {type:"status.loaded";status:MonitorStatus}
 | {type:"probes.loaded";probes:readonly ProbeInfo[]}
 | {type:"groups.loaded";groups:readonly WatchGroup[];submittedDraft?:GroupDraft;createdGroupId?:string}
 | {type:"group.acknowledged";group:WatchGroup;submittedDraft:GroupDraft}
 | {type:"catalog.loaded";catalog:"variables";query:string;bindingKey:string;cursor:string|null;items:readonly VariableDescriptor[];nextCursor:string|null}
 | {type:"catalog.loaded";catalog:"registers";query:string;bindingKey:string;cursor:string|null;items:readonly RegisterDescriptor[];nextCursor:string|null}
 | {type:"group.selected";groupId:string|null}
 | {type:"group.draft.changed";draft:GroupDraft}
 | {type:"group.watch.added";watch:WatchItem}
 | {type:"group.watch.removed";key:string}
 | {type:"series.toggled";key:string}
 | {type:"zoom.changed";action:import("../chart/zoom").ZoomAction}
 | {type:"zoom.reset"}
 | {type:"history.loaded";page:HistoryPage;query:HistoryQuery;navigation?:"replace"|"next"|"previous"}
 | {type:"export.loaded";artifact:ExportArtifact;submitted?:{exportId:string;startNs:bigint;endNs:bigint;format:"csv"|"jsonl"}}
 ;
export type MonitorAction=LoadedAction
 | {type:"request.started";scope:RequestScope;requestId:bigint}
 | {type:"request.succeeded";scope:RequestScope;requestId:bigint;data?:LoadedAction}
 | {type:"request.cleared";scope:RequestScope;requestId:bigint}
 | {type:"request.failed";scope:RequestScope;requestId:bigint;code:string;message:string;recovery?:RecoveryKind;summary?:string;fatal?:boolean}
 | {type:"request.dismissed";scope:RequestScope;requestId:bigint}
 | {type:"request.retired";scope:RequestScope;requestId:bigint}
 | {type:"request.reconciling";scope:RequestScope;requestId:bigint}
 | {type:"request.reconciled";scope:RequestScope;requestId:bigint}
 | {type:"access.blocked";code:string;message:string}
 | {type:"live.envelope";value:import("../api/contract").ParsedLiveEnvelope}
 | {type:"transport.open"}|{type:"transport.stale"};

export const emptyDraft:GroupDraft={sourceGroupId:null,expectedRevision:null,name:"",description:"",intervalMs:250,items:[]};
export const draftFromGroup=(group:WatchGroup):GroupDraft=>({sourceGroupId:group.groupId,expectedRevision:group.revision,name:group.name,description:group.description,intervalMs:group.intervalMs,items:[...group.items]});
