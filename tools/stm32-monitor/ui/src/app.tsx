import type {JSX} from "preact";
import {useEffect,useReducer,useMemo,useRef} from "preact/hooks";
import {createMonitorApi} from "./api/client";
import {createController,type Controller} from "./controller";
import {initialState,reducer} from "./state/reducer";
import {
  chartSeries,
  liveRows,
  selectedGroup,
} from "./state/selectors";
import type {DisplaySeries} from "./state/model";
import {displayDropTotals} from "./chart/series";
import {IdentityBar} from "./components/IdentityBar";
import {ProbePanel} from "./components/ProbePanel";
import {CatalogPanel} from "./components/CatalogPanel";
import {GroupPanel} from "./components/GroupPanel";
import {LiveTable} from "./components/LiveTable";
import {LiveChart} from "./components/LiveChart";
import {ChartZoomControls} from "./components/ChartZoomControls";
import {StatusStrip} from "./components/StatusStrip";
import {NoticeRegion} from "./components/NoticeRegion";
import {HistoryPanel} from "./components/HistoryPanel";
import {ExportPanel} from "./components/ExportPanel";

export function App():JSX.Element{
  const [state,dispatch]=useReducer(reducer,initialState);
  const stateRef=useRef(state);
  stateRef.current=state;
  const controllerRef=useRef<Controller|null>(null);
  if(controllerRef.current===null){
    controllerRef.current=createController(createMonitorApi(fetch,window.location.origin),dispatch,()=>stateRef.current);
  }
  const controller=controllerRef.current;

  useEffect(()=>{
    void controller.loadInitial();
    return()=>{controller.close();};
  },[controller]);

  const series:readonly DisplaySeries[]=chartSeries(state);
  const rows=liveRows(state);
  const group=selectedGroup(state);
  const status=state.status;
  const drops=displayDropTotals(state.live);
  const currentExportRange=useMemo(()=>{
    const history=state.history.query;
    if(history!==null)return{startNs:history.startNs,endNs:history.endNs};
    return{startNs:0n,endNs:0n};
  },[state.history.query]);

  if(state.blockingError!==null){
    return<main aria-label="STM32 Monitor"><p role="alert">{state.blockingError.code}: {state.blockingError.message}</p></main>;
  }
  if(status===null){
    return<main aria-label="STM32 Monitor"><p>Monitor is loading</p></main>;
  }
  const historyQuery=state.history.query??{startNs:0n,endNs:0n};

  return<main aria-label="STM32 Monitor" className="monitor-shell">
    <IdentityBar project={status.project} firmware={status.firmware} onCopy={()=>{void navigator.clipboard?.writeText(JSON.stringify({workspaceId:status.workspaceId,sessionId:status.sessionId}));}}/>
    <ProbePanel probes={state.probes} connectedProbeId={status.probe.probeId} canReconnect={status.probe.connected}
      leaseReason={null} onRefresh={()=>controller.refreshProbes()} onConnect={(id)=>controller.connectProbe(id)}
      onReconnect={()=>controller.reconnectProbe()} onRelease={()=>controller.releaseProbe()}/>
    <CatalogPanel connected={status.probeConnected} bindingEpoch={state.status?.sampling.bindingEpoch??0n}
      variables={state.catalog.variables} registers={state.catalog.registers}
      onSearch={(kind,query)=>controller.searchCatalog(kind,query)} onNext={(kind)=>controller.nextCatalog(kind)}
      onAdd={(watch)=>dispatch({type:"group.watch.added",watch})}/>
    <GroupPanel groups={state.groups} selectedGroupId={state.selectedGroupId} draft={state.groupDraft}
      failure={state.failures["groups.create"]??state.failures["groups.update"]??state.failures["groups.delete"]??null}
      onSelect={(groupId)=>dispatch({type:"group.selected",groupId})}
      onDraftChange={(draft)=>dispatch({type:"group.draft.changed",draft})}
      onRemove={(key)=>dispatch({type:"group.watch.removed",key})}
      onCreate={()=>controller.createGroup()} onSave={()=>controller.saveGroup(state.groupDraft)}
      onDelete={(groupId)=>controller.deleteGroup(groupId)}
      onReadImport={async()=>({ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import file is invalid"})}
      onImport={(value)=>controller.importGroups(value)}
      onExport={()=>controller.refreshGroups()} onRefresh={()=>controller.refreshGroups()}/>
    <LiveTable rows={rows} selectedSeries={[...state.selectedSeries]} onSeriesToggle={(key)=>dispatch({type:"series.toggled",key})}/>
    <LiveChart series={series} range={state.zoom} onZoom={(range)=>dispatch({type:"zoom.changed",action:{type:"zoom.set",start:range.start,end:range.end}})}/>
    <ChartZoomControls range={state.zoom} onAction={(action)=>dispatch({type:"zoom.changed",action})}/>
    <StatusStrip actualRateHz={state.live.actualRateHz} latencyNs={state.live.latencyNs} drops={drops}/>
    <NoticeRegion notices={state.notices}/>
    <HistoryPanel query={historyQuery} page={state.history.page} failure={state.failures["history"]??null}
      onLoad={(query)=>controller.loadHistory(query)} onPage={(cursor)=>controller.nextHistory(cursor)}/>
    <ExportPanel range={currentExportRange} artifact={state.exports.artifact}
      failure={state.failures["export.create"]??state.failures["export.status"]??state.failures["export.download"]??null}
      onCreate={({startNs,endNs,format})=>controller.createExport(startNs,endNs,format)}
      onRefresh={(exportId)=>controller.refreshExport(exportId)}
      onDownload={(exportId)=>controller.downloadExport(exportId)}/>
  </main>;
}
