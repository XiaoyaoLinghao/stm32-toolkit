import type {JSX} from "preact";
import {useEffect,useReducer,useRef,useState} from "preact/hooks";
import {createMonitorApi} from "./api/client";
import {createController,type Controller} from "./controller";
import {initialState,reducer} from "./state/reducer";
import {chartSeries,liveRows,selectedGroup} from "./state/selectors";
import {emptyDraft} from "./state/model";
import {displayDropTotals} from "./chart/series";
import {copy} from "./presentation/zh";
import {IdentityBar} from "./components/IdentityBar";
import {ProbePanel} from "./components/ProbePanel";
import {CatalogPanel} from "./components/CatalogPanel";
import {GroupPanel} from "./components/GroupPanel";
import {SamplingControls} from "./components/SamplingControls";
import {LiveTable} from "./components/LiveTable";
import {LiveChart} from "./components/LiveChart";
import {ChartZoomControls} from "./components/ChartZoomControls";
import {StatusStrip} from "./components/StatusStrip";
import {NoticeRegion} from "./components/NoticeRegion";
import {HistoryPanel} from "./components/HistoryPanel";
import {ExportPanel} from "./components/ExportPanel";
import {FailureMessage} from "./components/FailureMessage";
import {TransportStatus} from "./components/TransportStatus";
import {OperationRegion} from "./components/OperationRegion";

export function App():JSX.Element{
  const [state,dispatch]=useReducer(reducer,initialState);
  const [view,setView]=useState<"live"|"history">("live");
  const [catalogOpen,setCatalogOpen]=useState(false);
  const [deviceOpen,setDeviceOpen]=useState(false);
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

  if(state.blockingError!==null){
    return<main className="blocking-screen" aria-label={copy.app}>
      <h1>{copy.app}</h1><FailureMessage failure={state.blockingError} blocked/>
    </main>;
  }
  const status=state.status;
  if(status===null){
    return<main className="blocking-screen" aria-label={copy.app}><h1>{copy.app}</h1>
      {state.pending.initial!==undefined&&<p role="status">{copy.loading}</p>}
      <OperationRegion failures={state.failures} pending={state.pending} reconciling={state.reconciling}
        allowDismissInitial={false}
        onRetry={(scope,id)=>controller.retry(scope,id)} onDismiss={(scope,id)=>controller.dismiss(scope,id)}/>
    </main>;
  }

  const currentExportRange=state.history.query===null?null:{startNs:state.history.query.startNs,endNs:state.history.query.endNs};
  const fresh=status.sampling.state==="RUNNING"&&state.transport.open&&!state.transport.stale;
  const liveView=view==="live";
  const busyGroups=["groups.create","groups.update","groups.delete","groups.import","groups.list"].some(scope=>state.pending[scope as keyof typeof state.pending]!==undefined);
  const busyProbe=["probe.connect","probe.reconnect","probe.release","status"].some(scope=>state.pending[scope as keyof typeof state.pending]!==undefined);
  const busySampling=["sampling.start","sampling.pause","sampling.resume","sampling.stop","status"].some(scope=>state.pending[scope as keyof typeof state.pending]!==undefined);

  return<main aria-label={copy.app} className="monitor-shell">
    <header className="workbench-header">
      <div className="brand"><strong>{copy.app}</strong><span>{status.project.name} · <code>{status.project.targetDevice}</code></span></div>
      <div className="header-status"><span>{status.probe.connected?copy.probeConnected:copy.probeDisconnected}</span>
        <TransportStatus sampling={status.sampling.state} open={state.transport.open} stale={state.transport.stale}/></div>
      <button type="button" aria-expanded={deviceOpen} aria-controls="device-details" onClick={()=>setDeviceOpen(open=>!open)}>{copy.device}</button>
    </header>
    <nav className="main-nav" aria-label={copy.mainNav}>
      <button type="button" className={liveView?"active":""} aria-current={liveView?"page":undefined} onClick={()=>setView("live")}>{copy.live}</button>
      <button type="button" className={!liveView?"active":""} aria-current={!liveView?"page":undefined} onClick={()=>setView("history")}>{copy.history}</button>
    </nav>
    <OperationRegion failures={state.failures} pending={state.pending} reconciling={state.reconciling}
      onRetry={(scope,id)=>controller.retry(scope,id)} onDismiss={(scope,id)=>controller.dismiss(scope,id)}/>
    <div className="device-details" id="device-details" hidden={!deviceOpen}>
      <div className="device-heading"><h2>{copy.device}</h2><button type="button" onClick={()=>setDeviceOpen(false)}>{copy.close}</button></div>
      <div className="device-grid"><IdentityBar project={status.project} firmware={status.firmware}
        onCopy={()=>{void navigator.clipboard?.writeText(JSON.stringify({workspaceId:status.workspaceId,sessionId:status.sessionId}));}}/>
      <ProbePanel probes={state.probes} connectedProbeId={status.probe.probeId} canReconnect={status.probe.connected} busy={busyProbe}
        leaseReason={null} onRefresh={()=>controller.refreshProbes()} onConnect={(id)=>controller.connectProbe(id)}
        onReconnect={()=>controller.reconnectProbe()} onRelease={()=>controller.releaseProbe()}/></div>
    </div>
    <div className="workspace live-workspace" hidden={!liveView}>
      <aside className="watch-sidebar" aria-label={copy.watchConfig}>
        <GroupPanel compact groups={state.groups} selectedGroupId={state.selectedGroupId} draft={state.groupDraft}
          failure={null} busy={busyGroups}
          onSelect={(groupId)=>dispatch({type:"group.selected",groupId})}
          onDraftChange={(draft)=>dispatch({type:"group.draft.changed",draft})}
          onRemove={(key)=>dispatch({type:"group.watch.removed",key})}
          onNew={()=>dispatch({type:"group.draft.changed",draft:emptyDraft})}
          onSave={()=>controller.saveGroup(state.groupDraft)}
          onDelete={(groupId)=>controller.deleteGroup(groupId)}
          onImport={(value)=>controller.importGroups(value)}
          onExport={()=>controller.refreshGroups()}/>
        <button type="button" className="catalog-toggle" aria-expanded={catalogOpen} aria-controls="catalog-container" onClick={()=>setCatalogOpen(open=>!open)}>{catalogOpen?copy.catalogCollapse:copy.catalogBrowse}</button>
        <div id="catalog-container" hidden={!catalogOpen}>
          <CatalogPanel connected={status.probeConnected} bindingEpoch={status.sampling.bindingEpoch}
            variables={state.catalog.variables} registers={state.catalog.registers}
            pending={state.pending["catalog.variables"]!==undefined||state.pending["catalog.registers"]!==undefined}
            onSearch={(kind,query)=>controller.searchCatalog(kind,query)} onNext={(kind)=>controller.nextCatalog(kind)}
            onAdd={(watch)=>dispatch({type:"group.watch.added",watch})}/>
        </div>
      </aside>
      <div className="live-main">
        <SamplingControls status={status.sampling} group={selectedGroup(state)} busy={busySampling}
          onStart={(groupId,revision)=>controller.startSampling(groupId,revision)}
          onPause={()=>controller.pauseSampling()} onResume={()=>controller.resumeSampling()}
          onStop={()=>controller.stopSampling()}
          failure={null}/>
        <LiveChart series={chartSeries(state)} range={state.zoom} visible={liveView}
          onZoom={(range)=>dispatch({type:"zoom.changed",action:{type:"zoom.set",start:range.start,end:range.end}})}/>
        <ChartZoomControls range={state.zoom} onAction={(action)=>dispatch({type:"zoom.changed",action})}/>
        <LiveTable rows={liveRows(state)} selectedSeries={[...state.selectedSeries]} fresh={fresh}
          onSeriesToggle={(key)=>dispatch({type:"series.toggled",key})}/>
      </div>
    </div>
    <div className="history-workspace" hidden={liveView}>
      <HistoryPanel query={state.history.query} page={state.history.page} cursorStack={state.history.cursorStack}
        busy={state.pending.history!==undefined} failure={null}
        onLoad={(query)=>controller.loadHistory(query)} onPage={(cursor)=>controller.nextHistory(cursor)}/>
      <ExportPanel range={currentExportRange} artifact={state.exports.artifact} submitted={state.exports.submitted}
        creating={state.pending["export.create"]!==undefined} refreshing={state.pending["export.status"]!==undefined}
        downloading={state.pending["export.download"]!==undefined}
        failure={null}
        onCreate={({startNs,endNs,format})=>controller.createExport(startNs,endNs,format)}
        onRefresh={(exportId)=>controller.refreshExport(exportId)}
        onDownload={(exportId)=>controller.downloadExport(exportId)}/>
    </div>
    <NoticeRegion notices={state.notices}/>
    <StatusStrip actualRateHz={state.live.actualRateHz} latencyNs={state.live.latencyNs} drops={displayDropTotals(state.live)}/>
  </main>;
}
