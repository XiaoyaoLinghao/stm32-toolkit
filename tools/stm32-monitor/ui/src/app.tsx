import type {JSX} from "preact";
import {useEffect,useReducer,useRef,useState} from "preact/hooks";
import {createMonitorApi} from "./api/client";
import {createController,type Controller} from "./controller";
import {initialState,reducer} from "./state/reducer";
import {activeGroup,chartSeries,liveRows,selectedGroup} from "./state/selectors";
import {groupDirty,groupSourceProblem,groupWorkflowBusy,type RequestScope} from "./state/model";
import {displayDropTotals} from "./chart/series";
import {copy,formatCopy} from "./presentation/zh";
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
import {useDialogFocus} from "./components/dialog-focus";

type Drawer="device"|"group"|"diagnostics"|null;

export function App():JSX.Element{
  const [state,dispatch]=useReducer(reducer,initialState);
  const [view,setView]=useState<"live"|"history">("live");
  const [directoryOpen,setDirectoryOpen]=useState(true);
  const [valuesCollapsed,setValuesCollapsed]=useState(false);
  const [chartMaximized,setChartMaximized]=useState(false);
  const [activeDrawer,setActiveDrawer]=useState<Drawer>(null);
  const groupEntryRef=useRef<HTMLButtonElement>(null);
  const directoryToggleRef=useRef<HTMLButtonElement>(null);
  const stateRef=useRef(state);
  stateRef.current=state;
  const controllerRef=useRef<Controller|null>(null);
  if(controllerRef.current===null){
    controllerRef.current=createController(createMonitorApi(fetch,window.location.origin),dispatch,()=>stateRef.current);
  }
  const controller=controllerRef.current;
  const closeDrawer=()=>{if(stateRef.current.groupNavigation===null)setActiveDrawer(null);};
  const deviceDialog=useDialogFocus(activeDrawer==="device",closeDrawer);
  const groupDialog=useDialogFocus(activeDrawer==="group",closeDrawer,()=>directoryToggleRef.current);
  const diagnosticsDialog=useDialogFocus(activeDrawer==="diagnostics",closeDrawer);
  const openDrawer=(name:Exclude<Drawer,null>,trigger:HTMLElement|null)=>{
    if(trigger!==null){
      if(name==="device")deviceDialog.rememberTrigger(trigger);
      else if(name==="group")groupDialog.rememberTrigger(trigger);
      else diagnosticsDialog.rememberTrigger(trigger);
    }
    setActiveDrawer(name);
  };

  useEffect(()=>{
    void controller.loadInitial();
    return()=>{controller.close();};
  },[controller]);
  useEffect(()=>{
    if(state.groupNavigation!==null)setActiveDrawer("group");
  },[state.groupNavigation]);

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
  const runningGroup=activeGroup(state),runId=status.sampling.runId;
  const fresh=status.sampling.state==="RUNNING"&&state.transport.open&&!state.transport.stale&&!state.transport.needsStatusRefresh&&
    runningGroup!==null&&state.live.runId===runId;
  const liveView=view==="live";
  const busyGroups=groupWorkflowBusy(state);
  const liveBusy=state.transport.phase==="checking"||state.transport.phase==="connecting";
  const busyProbe=liveBusy||["probe.connect","probe.reconnect","probe.release","status"].some(scope=>state.pending[scope as keyof typeof state.pending]!==undefined);
  const busySampling=liveBusy||["sampling.start","sampling.pause","sampling.resume","sampling.stop","status"].some(scope=>state.pending[scope as keyof typeof state.pending]!==undefined);
  const reconnectBlocked=state.pending.status!==undefined||["probe.connect","probe.reconnect","probe.release","sampling.start","sampling.pause","sampling.resume","sampling.stop"].some(scope=>state.pending[scope as keyof typeof state.pending]!==undefined);
  const retryDisabledScopes:RequestScope[]=liveBusy?["status","probe.connect","probe.reconnect","probe.release","sampling.start","sampling.pause","sampling.resume","sampling.stop"]:[];
  if(reconnectBlocked)retryDisabledScopes.push("live.reconnect");
  if(busyGroups)retryDisabledScopes.push("groups.list","groups.create","groups.update","groups.delete","groups.import");
  const failureCount=Object.values(state.failures).filter(failure=>failure!==undefined).length;
  const dirty=groupDirty(state);
  const rows=liveRows(state);
  const rowClass=rows.length<=1?"one-row":rows.length===2?"two-rows":rows.length===3?"three-rows":"many-rows";
  const selected=selectedGroup(state);
  const groupName=state.groupDraft.name||selected?.name||copy.samplingNoGroup;

  return<main aria-label={copy.app} className="monitor-shell">
    <header className="workbench-header">
      <div className="brand"><strong>Monitor</strong></div>
      <nav className="main-nav" aria-label={copy.mainNav}>
        <button type="button" className={liveView?"active":""} aria-current={liveView?"page":undefined} onClick={()=>setView("live")}>{copy.live}</button>
        <button type="button" className={!liveView?"active":""} aria-current={!liveView?"page":undefined} onClick={()=>setView("history")}>{copy.history}</button>
      </nav>
      <div className="header-status"><span>{status.project.name} · {status.project.targetDevice}</span>
        <span>{status.probe.connected?copy.probeConnected:copy.probeDisconnected}</span>
        <TransportStatus sampling={status.sampling.state} phase={state.transport.phase} stale={state.transport.stale}/></div>
      <button type="button" className="header-device" aria-label={copy.device} aria-expanded={activeDrawer==="device"} aria-controls="device-details"
        onClick={event=>openDrawer("device",event.currentTarget)}>{copy.device}</button>
    </header>

    <div className="workbench-body">
      <div className={"workspace live-workspace "+(!directoryOpen?"directory-closed ":"")+(chartMaximized?"chart-maximized":"")} hidden={!liveView}>
        <aside className="watch-sidebar" aria-label={copy.watchConfig} hidden={!directoryOpen||chartMaximized}>
          <div className="sidebar-group">
            <small>{copy.groupTitle}</small><strong title={groupName}>{groupName}</strong>
            <span className={dirty?"group-dirty":""}>{dirty?formatCopy.draftCount(state.groupDraft.items.length):copy.groupSaved}</span>
            <button ref={groupEntryRef} type="button" onClick={event=>openDrawer("group",event.currentTarget)}>{copy.groupEditSave}</button>
            <button type="button" className="sidebar-close" aria-label={copy.directoryClosePanel} onClick={()=>setDirectoryOpen(false)}>{copy.close}</button>
          </div>
          <CatalogPanel connected={status.probeConnected} bindingEpoch={status.sampling.bindingEpoch}
            bindingKey={status.workspaceId+"/"+status.sessionId+"/"+status.project.logicalProjectId+"/"+status.sampling.bindingEpoch}
            variables={state.catalog.variables} registers={state.catalog.registers}
            pending={state.pending["catalog.variables"]!==undefined||state.pending["catalog.registers"]!==undefined}
            editBusy={busyGroups||state.groupNavigation!==null}
            onSearch={(kind,query)=>controller.searchCatalog(kind,query)} onNext={(kind)=>controller.nextCatalog(kind)}
            onAdd={(watch)=>{dispatch({type:"group.watch.added",watch});openDrawer("group",groupEntryRef.current);}}/>
        </aside>
        <div className={"live-main "+rowClass+(valuesCollapsed?" values-collapsed":"")}>
          <div className="sampling-toolbar">
            <button ref={directoryToggleRef} type="button" className="directory-toggle" aria-label={directoryOpen?copy.directoryCollapse:copy.directoryExpand}
              aria-expanded={directoryOpen} onClick={()=>setDirectoryOpen(open=>!open)}>{directoryOpen?"☰":"☷"}</button>
            <SamplingControls status={status.sampling} group={selected} busy={busySampling}
              probeConnected={status.probe.connected} onConnectRequest={trigger=>openDrawer("device",trigger)}
              activeGroupName={runningGroup?.name??null}
              onStart={(groupId,revision)=>controller.startSampling(groupId,revision)}
              onPause={()=>controller.pauseSampling()} onResume={()=>controller.resumeSampling()}
              onStop={()=>controller.stopSampling()}
              failure={null}/>
            <button type="button" className="toolbar-detail" aria-label={copy.toolbarDevice} onClick={event=>openDrawer("device",event.currentTarget)}>ⓘ</button>
          </div>
          <LiveChart series={chartSeries(state)} range={state.zoom} visible={liveView}
            layoutKey={String(liveView)+":"+String(directoryOpen)+":"+String(valuesCollapsed)+":"+String(chartMaximized)}
            headerActions={<><ChartZoomControls compact range={state.zoom} onAction={(action)=>dispatch({type:"zoom.changed",action})}/>
              <button type="button" className="chart-maximize" aria-label={chartMaximized?copy.chartRestore:copy.chartMaximize}
                onClick={()=>setChartMaximized(value=>!value)}>{chartMaximized?copy.chartRestore:copy.chartMaximize}</button></>}
            onZoom={(range)=>dispatch({type:"zoom.changed",action:{type:"zoom.set",start:range.start,end:range.end}})}/>
          <div className="live-source" aria-label={copy.liveSource}>
            {runId===null?<span>{copy.liveSourcePreview}</span>:<>
              <span>{state.live.lastSampleCapturedAtUtc===null?copy.liveSourceAwaiting:fresh?copy.liveSourceCurrent:copy.liveSourcePrevious}：
                {copy.liveSourceGroup} {runningGroup?.name??copy.liveSourceUnknownGroup} ·
                {copy.liveSourceRevision} {status.sampling.groupRevision?.toString()??"-"}</span>
              {runningGroup===null&&<span className="stale-label">{state.live.lastSampleCapturedAtUtc===null?copy.liveSourceUnverifiedEmpty:copy.liveSourceUnverified}</span>}
            </>}
          </div>
          <div className={"values-region "+rowClass} hidden={chartMaximized}>
            <button type="button" className="values-collapse" aria-label={valuesCollapsed?copy.valuesExpand:copy.valuesCollapse}
              aria-expanded={!valuesCollapsed} onClick={()=>setValuesCollapsed(value=>!value)}>{valuesCollapsed?copy.valuesExpand:copy.valuesCollapse}</button>
            <LiveTable rows={rows} selectedSeries={[...state.selectedSeries]} fresh={fresh} collapsed={valuesCollapsed}
              onSeriesToggle={(key)=>dispatch({type:"series.toggled",key})}/>
          </div>
        </div>
      </div>
      <div className="history-workspace" hidden={liveView}>
        <HistoryPanel query={state.history.query} page={state.history.page} inFlight={state.history.inFlight} cursorStack={state.history.cursorStack}
          busy={state.pending.history!==undefined} failure={null}
          onLoad={(query)=>controller.loadHistory(query)} onPage={(cursor)=>controller.nextHistory(cursor)}/>
        <ExportPanel range={currentExportRange} artifact={state.exports.artifact} submitted={state.exports.submitted}
          creating={state.pending["export.create"]!==undefined} refreshing={state.pending["export.status"]!==undefined}
          downloading={state.pending["export.download"]!==undefined} failure={null}
          onCreate={({startNs,endNs,format})=>controller.createExport(startNs,endNs,format)}
          onRefresh={(exportId)=>controller.refreshExport(exportId)}
          onDownload={(exportId)=>controller.downloadExport(exportId)}/>
      </div>
    </div>

    <aside className="workbench-drawer" id="device-details" role="dialog" aria-modal="true" aria-label={copy.device} tabIndex={-1}
      ref={deviceDialog.dialogRef} onKeyDown={deviceDialog.onDialogKeyDown} hidden={activeDrawer!=="device"}>
      <div className="drawer-content"><div className="drawer-heading"><h2>{copy.device}</h2>
        <button type="button" aria-label={copy.closeDevice} onClick={closeDrawer}>{copy.close}</button></div>
        <IdentityBar project={status.project} firmware={status.firmware}
          onCopy={()=>{void navigator.clipboard?.writeText(JSON.stringify({workspaceId:status.workspaceId,sessionId:status.sessionId}));}}/>
        <ProbePanel probes={state.probes} connectedProbeId={status.probe.probeId} canReconnect={status.probe.connected} busy={busyProbe}
          leaseReason={null} onRefresh={()=>controller.refreshProbes()} onConnect={(id)=>controller.connectProbe(id)}
          onReconnect={()=>controller.reconnectProbe()} onRelease={()=>controller.releaseProbe()}/>
      </div>
    </aside>
    <aside className="workbench-drawer" role="dialog" aria-modal="true" aria-label={copy.groupTitle} tabIndex={-1}
      ref={groupDialog.dialogRef} onKeyDown={groupDialog.onDialogKeyDown} hidden={activeDrawer!=="group"}>
      <div className="drawer-content"><div className="drawer-heading"><h2>{copy.groupTitle}</h2>
        <button type="button" aria-label={copy.closeGroup} disabled={state.groupNavigation!==null} onClick={closeDrawer}>{copy.close}</button></div>
        <GroupPanel editorOpen groups={state.groups} selectedGroupId={state.selectedGroupId} draft={state.groupDraft}
          dirty={dirty} navigation={state.groupNavigation} navigationMissing={state.groupNavigationMissing}
          sourceProblem={groupSourceProblem(state)} editorGeneration={state.groupGeneration}
          nameReviewRequired={state.groupNameReviewRequired} needsRefresh={state.groupsNeedRefresh}
          failure={null} busy={busyGroups}
          onSelect={(groupId)=>dispatch({type:"group.navigation.requested",target:{kind:"group",groupId}})}
          onDraftChange={(draft)=>dispatch({type:"group.draft.changed",draft})}
          onRemove={(key)=>dispatch({type:"group.watch.removed",key})}
          onNew={()=>dispatch({type:"group.navigation.requested",target:{kind:"new"}})}
          onNavigateConfirm={()=>dispatch({type:"group.navigation.confirmed"})}
          onNavigateCancel={()=>dispatch({type:"group.navigation.cancelled"})}
          onSaveAsNew={()=>dispatch({type:"group.save-as-new"})}
          onNameReviewed={()=>dispatch({type:"group.name.reviewed"})}
          onReload={()=>{const groupId=state.groupDraft.sourceGroupId;if(groupId!==null)dispatch({type:"group.navigation.requested",target:{kind:"reload",groupId}});}}
          onSave={()=>controller.saveGroup(state.groupDraft)}
          onDelete={(groupId,revision,generation)=>controller.deleteGroup(groupId,revision,generation)}
          onImport={(value)=>controller.importGroups(value)}
          onExport={()=>controller.refreshGroups()} onRefresh={()=>controller.refreshGroups()}/>
      </div>
    </aside>
    <aside className="workbench-drawer" role="dialog" aria-modal="true" aria-label={copy.diagnostics} tabIndex={-1}
      ref={diagnosticsDialog.dialogRef} onKeyDown={diagnosticsDialog.onDialogKeyDown} hidden={activeDrawer!=="diagnostics"}>
      <div className="drawer-content"><div className="drawer-heading"><h2>{copy.diagnostics}</h2>
        <button type="button" aria-label={copy.closeDiagnostics} onClick={closeDrawer}>{copy.close}</button></div>
        {(state.transport.phase==="disconnected"||liveBusy||state.transport.needsStatusRefresh)&&<div className="live-recovery" aria-label={copy.liveReconnect}>
          {state.transport.phase==="disconnected"&&<button type="button" disabled={reconnectBlocked} onClick={()=>void controller.reconnectLive()}>{copy.liveReconnect}</button>}
          {liveBusy&&<button type="button" onClick={()=>controller.cancelLiveReconnect()}>{copy.liveCancel}</button>}
          {state.transport.needsStatusRefresh&&<><span role="status">{copy.statusRefreshNeeded}</span>
            <button type="button" disabled={liveBusy||state.pending.status!==undefined} onClick={()=>void controller.refreshStatus()}>{copy.statusRefresh}</button></>}
        </div>}
        <OperationRegion failures={state.failures} pending={state.pending} reconciling={state.reconciling} retryDisabledScopes={retryDisabledScopes}
          onRetry={(scope,id)=>controller.retry(scope,id)} onDismiss={(scope,id)=>controller.dismiss(scope,id)}/>
        <section className="runtime-identity" aria-label={copy.runtimeIdentity}><h3>{copy.runtimeIdentity}</h3>
          <p>{copy.historyRun}：<code>{runId??"-"}</code></p>
          <p>{copy.liveSourceGroup}：<code>{status.sampling.groupId??"-"}</code></p>
          <p>{copy.liveSourceRevision}：<code>{status.sampling.groupRevision?.toString()??"-"}</code></p>
        </section>
        <NoticeRegion notices={state.notices}/>
      </div>
    </aside>
    <div className="workbench-footer"><StatusStrip actualRateHz={state.live.actualRateHz} latencyNs={state.live.latencyNs}
      lastSampleCapturedAtUtc={state.live.lastSampleCapturedAtUtc} fresh={fresh} drops={displayDropTotals(state.live)}/>
      <button type="button" className={failureCount>0?"problem-entry has-problems":"problem-entry"} aria-label={formatCopy.problemCount(failureCount)}
        onClick={event=>openDrawer("diagnostics",event.currentTarget)}>{formatCopy.problemCount(failureCount)}</button></div>
  </main>;
}
