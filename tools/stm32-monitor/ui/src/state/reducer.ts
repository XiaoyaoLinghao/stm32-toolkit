import type {MonitorStatus,ObservationBinding,ParsedLiveEnvelope} from "../api/contract";
import {appendAuthoritativeSample,appendContinuityGap,emptyLive,addSampleDropDeltas,watchKey,projectHistoryPage} from "../chart/series";
import {initialZoom,zoomReducer} from "../chart/zoom";
import {draftFromGroup,emptyDraft,groupDirty,groupWorkflowBusy,sameGroupContent,sourceContextKey,type DropTotals,type GroupNavigation,type LiveState,type MonitorAction,type MonitorState,type RequestScope,type SourceCatalogState} from "./model";

const zeroDrops=():DropTotals=>({subscriber:0n,history:0n,deadline:0n,service:0n});
const dropsFrom=(status:MonitorStatus):DropTotals=>({subscriber:status.sampling.subscriberDrops,history:status.sampling.historyDrops,deadline:status.sampling.deadlineDrops,service:status.sampling.serviceDrops});
const liveForStatus=(status:MonitorStatus,selected:ReadonlySet<string>):LiveState=>({...emptyLive(),selectedSeries:new Set([...selected].slice(0,8)),bindingEpoch:status.sampling.bindingEpoch,runId:status.sampling.runId,authoritativeDrops:dropsFrom(status)});
const emptyProjection={rows:[],series:new Map()};
const emptySource=(generation=0n):SourceCatalogState=>({query:"",initialized:false,generation,contextKey:"",page:null,children:{},lastAddedId:null});
export const initialState:MonitorState={status:null,probes:[],groups:[],selectedGroupId:null,groupDraft:emptyDraft,groupBaseline:emptyDraft,groupGeneration:0n,groupNavigation:null,groupNavigationMissing:false,groupNameReviewRequired:false,groupWriteBusy:false,groupsNeedRefresh:false,stateRevision:-1n,lastAcceptedEventId:null,pending:{},reconciling:{},failures:{},catalog:{variables:null,registers:null,source:emptySource()},selectedSeries:new Set(),live:emptyLive(),zoom:initialZoom,transport:{phase:"idle",open:false,stale:true,needsStatusRefresh:false,gapRevision:0n},history:{query:null,page:null,projection:emptyProjection,cursorIndex:0,cursorStack:[],nextCursor:null,inFlight:null},exports:{artifact:null,submitted:null},notices:[],blockingError:null};
const sameBinding=(a:ObservationBinding,b:ObservationBinding):boolean=>a.workspaceId===b.workspaceId&&a.sessionId===b.sessionId&&a.logicalProjectId===b.logicalProjectId&&a.probeId===b.probeId&&a.targetDevice===b.targetDevice&&a.physicalTarget===b.physicalTarget&&a.buildId===b.buildId&&a.elfSha256===b.elfSha256&&a.inputSnapshotSha256===b.inputSnapshotSha256&&a.gitHead===b.gitHead&&a.gitDirty===b.gitDirty&&a.flashSessionId===b.flashSessionId&&a.leaseId===b.leaseId&&a.dwarfSha256===b.dwarfSha256&&a.svdSha256===b.svdSha256;
const statusMatches=(status:MonitorStatus,binding:ObservationBinding):boolean=>status.workspaceId===binding.workspaceId&&status.sessionId===binding.sessionId&&status.project.logicalProjectId===binding.logicalProjectId&&status.project.targetDevice===binding.targetDevice&&status.probe.connected&&status.probe.probeId===binding.probeId&&status.firmware!==null&&status.firmware.buildId===binding.buildId&&status.firmware.elfSha256===binding.elfSha256&&status.firmware.inputSnapshotSha256===binding.inputSnapshotSha256&&status.firmware.gitHead===binding.gitHead&&status.firmware.gitDirty===binding.gitDirty&&status.firmware.targetDevice===binding.targetDevice;
const catalogBindingKey=(status:MonitorStatus):string=>`${status.workspaceId}/${status.sessionId}/${status.project.logicalProjectId}/${status.sampling.bindingEpoch}`;
const uniqueCatalogItems=<T extends {selector:string}>(prior:readonly T[],incoming:readonly T[]):readonly T[]=>{
 const seen=new Set(prior.map(item=>item.selector));
 const result=[...prior];
 for(const item of incoming)if(!seen.has(item.selector)){seen.add(item.selector);result.push(item);}
 return result;
};
const rebased=(live:LiveState,status:MonitorStatus):LiveState=>({...live,authoritativeDrops:dropsFrom(status),pendingDropDeltas:zeroDrops(),bindingEpoch:status.sampling.bindingEpoch,runId:status.sampling.runId});
const sameFirmware=(left:MonitorStatus["firmware"],right:MonitorStatus["firmware"]):boolean=>left===null?right===null:right!==null&&left.buildId===right.buildId&&left.elfSha256===right.elfSha256&&left.inputSnapshotSha256===right.inputSnapshotSha256&&left.gitHead===right.gitHead&&left.gitDirty===right.gitDirty&&left.targetDevice===right.targetDevice;
const resetForStatus=(state:MonitorState,status:MonitorStatus):boolean=>{const prior=state.status;return prior!==null&&(prior.workspaceId!==status.workspaceId||prior.sessionId!==status.sessionId||prior.project.logicalProjectId!==status.project.logicalProjectId||prior.project.targetDevice!==status.project.targetDevice||!sameFirmware(prior.firmware,status.firmware)||prior.probe.connected!==status.probe.connected||prior.probe.probeId!==status.probe.probeId||prior.sampling.bindingEpoch!==status.sampling.bindingEpoch||prior.sampling.runId!==status.sampling.runId);};
const resetNotice=(state:MonitorState,text:string)=>state.notices.some(notice=>notice.kind==="view-reset"&&notice.text===text)
  ?state.notices:[...state.notices,{id:`view-reset-${state.notices.length}`,kind:"view-reset" as const,text}];
const sameDraft=(left:MonitorState["groupDraft"],right:MonitorState["groupDraft"]):boolean=>
  left.sourceGroupId===right.sourceGroupId&&left.expectedRevision===right.expectedRevision&&sameGroupContent(left,right);
const groupFailureScopes=["groups.create","groups.update","groups.delete","groups.import"] as const;
function withoutConflictFailures(state:MonitorState):MonitorState{
  const failures={...state.failures};
  for(const scope of groupFailureScopes)if(failures[scope]?.recovery==="groups-refresh")delete failures[scope];
  return {...state,failures};
}
function navigate(state:MonitorState,target:GroupNavigation):MonitorState{
  const source=target.kind==="new"?null:state.groups.find(group=>group.groupId===target.groupId)??null;
  if(target.kind!=="new"&&source===null)return {...state,groupNavigation:null,groupNavigationMissing:true};
  const draft=source===null?emptyDraft:draftFromGroup(source);
  return withoutConflictFailures({...state,selectedGroupId:source?.groupId??null,groupDraft:draft,groupBaseline:draft,
    groupGeneration:state.groupGeneration+1n,groupNavigation:null,groupNavigationMissing:false,groupNameReviewRequired:false});
}
const catalogScopes=["catalog.variables","catalog.registers"] as const;
const sourceScopes=["catalog.source","catalog.source-child","catalog.source-selection"] as const;
function retireSource(state:MonitorState):MonitorState{
 const retired=retireScopes(state,sourceScopes);
 return{...retired,catalog:{...retired.catalog,source:emptySource(retired.catalog.source.generation+1n)}};
}
function retireScopes(state:MonitorState,scopes:readonly RequestScope[]):MonitorState{
 const pending={...state.pending},failures={...state.failures},reconciling={...state.reconciling};
 for(const scope of scopes){delete pending[scope];delete failures[scope];delete reconciling[scope];}
 return {...state,pending,failures,reconciling};
}
const settledHistory=(state:MonitorState,scope:RequestScope,requestId:bigint):MonitorState["history"]=>
 scope==="history"&&state.history.inFlight?.requestId===requestId?{...state.history,inFlight:null}:state.history;

export function reduceAcceptedLiveEnvelope(state:MonitorState,envelope:ParsedLiveEnvelope):MonitorState{
  const {event,subscriberDropped}=envelope;if(state.lastAcceptedEventId!==null&&event.eventId<=state.lastAcceptedEventId)return state;
  const gap=subscriberDropped>0n||event.type==="state"&&event.data.gap;
  let next:MonitorState={...state,lastAcceptedEventId:event.eventId,transport:gap?{...state.transport,stale:true,needsStatusRefresh:true,gapRevision:state.transport.gapRevision+1n}:state.transport};
  if(subscriberDropped>0n)next={...next,live:appendContinuityGap(next.live),zoom:initialZoom};
  if(event.type==="hello"||event.type==="heartbeat")return {...next,stateRevision:event.data.stateRevision>state.stateRevision?event.data.stateRevision:state.stateRevision};
 if(event.type==="state"){
  if(event.data.stateRevision<state.stateRevision)return next;const changed=resetForStatus(state,event.data.status);let live=changed?liveForStatus(event.data.status,state.selectedSeries):rebased(next.live,event.data.status);const gap=event.data.gap||subscriberDropped>0n;if(event.data.gap&&subscriberDropped===0n)live=appendContinuityGap(live);
   const sourceChanged=state.status!==null&&sourceContextKey(state.status)!==sourceContextKey(event.data.status);
   const updated={...next,status:event.data.status,stateRevision:event.data.stateRevision,live,zoom:changed||gap?initialZoom:next.zoom,catalog:changed?{...state.catalog,variables:null,registers:null}:state.catalog,transport:{...next.transport,stale:changed||gap||next.transport.stale},notices:changed||gap?resetNotice(state,changed?"Live view reset for a new binding or run":"Live event gap; status refresh required"):state.notices};
  const priorRetired=state.status!==null&&catalogBindingKey(state.status)!==catalogBindingKey(event.data.status)?retireScopes(updated,catalogScopes):updated;
  return sourceChanged?retireSource(priorRetired):priorRetired;
 }
 const batch=event.data.batch,group=state.groups.find(item=>item.groupId===batch.groupId&&item.revision===batch.groupRevision);
 if(state.status===null||group===undefined||!statusMatches(state.status,batch.binding)||state.status.sampling.bindingEpoch!==state.live.bindingEpoch||state.status.sampling.runId!==batch.runId||(state.live.binding!==null&&!sameBinding(state.live.binding,batch.binding)))return {...next,transport:{...next.transport,stale:true}};
 let live=addSampleDropDeltas({...state.live,selectedSeries:new Set([...state.selectedSeries].slice(0,8))},batch,event.data.serviceSubscriberDrops);live=appendAuthoritativeSample(live,batch,group,state.selectedSeries);if(subscriberDropped>0n)live=appendContinuityGap(live);
  return {...next,live,zoom:subscriberDropped>0n?initialZoom:state.zoom,transport:{...next.transport,stale:next.transport.needsStatusRefresh}};
}

export function reducer(state:MonitorState,action:MonitorAction):MonitorState{
 if(action.type==="request.succeeded"){
  if(state.blockingError!==null||state.pending[action.scope]?.requestId!==action.requestId)return state;
  const pending={...state.pending};delete pending[action.scope];
  const failures={...state.failures};delete failures[action.scope];
  const settled={...state,pending,failures,history:settledHistory(state,action.scope,action.requestId)};
  return action.data===undefined?settled:reducer(settled,action.data);
 }
 if(action.type==="request.dismissed"){
  if(state.failures[action.scope]?.requestId!==action.requestId)return state;
  const failures={...state.failures};delete failures[action.scope];
  const reconciling={...state.reconciling};delete reconciling[action.scope];
  return {...state,failures,reconciling};
 }
 if(action.type==="request.retired"){
  const pending={...state.pending},failures={...state.failures},reconciling={...state.reconciling};
  if(pending[action.scope]?.requestId===action.requestId)delete pending[action.scope];
  if(failures[action.scope]?.requestId===action.requestId)delete failures[action.scope];
  if(reconciling[action.scope]===action.requestId)delete reconciling[action.scope];
  return {...state,pending,failures,reconciling,history:settledHistory(state,action.scope,action.requestId)};
 }
 if(action.type==="request.reconciling")return state.failures[action.scope]?.requestId===action.requestId
  ?{...state,reconciling:{...state.reconciling,[action.scope]:action.requestId}}:state;
 if(action.type==="request.reconciled"){
  if(state.reconciling[action.scope]!==action.requestId)return state;
  const reconciling={...state.reconciling};delete reconciling[action.scope];
  return {...state,reconciling};
 }
  if(action.type==="access.blocked")return {...state,pending:{},reconciling:{},failures:{},history:{...state.history,inFlight:null},blockingError:{ok:false,code:action.code,message:action.message},transport:{...state.transport,phase:"disconnected",open:false,stale:true}};
 if(action.type==="live.envelope")return reduceAcceptedLiveEnvelope(state,action.value);
 if(action.type==="initial.loaded"){const selected=action.groups[0]??null;const draft=selected===null?emptyDraft:draftFromGroup(selected);const updated={...state,status:action.status,probes:action.probes,groups:action.groups,selectedGroupId:selected?.groupId??null,groupDraft:draft,groupBaseline:draft,groupGeneration:state.groupGeneration+1n,groupNavigation:null,groupNavigationMissing:false,groupNameReviewRequired:false,live:liveForStatus(action.status,state.selectedSeries)};const prior=state.status!==null&&catalogBindingKey(state.status)!==catalogBindingKey(action.status)?retireScopes(updated,catalogScopes):updated;return state.status===null||sourceContextKey(state.status)!==sourceContextKey(action.status)?retireSource(prior):prior;}
  if(action.type==="status.loaded"){
   const guarded=action.startedGapRevision!==undefined&&action.startedStateRevision!==undefined;
   if(guarded&&(action.startedGapRevision!==state.transport.gapRevision||action.startedStateRevision!==state.stateRevision))return state;
   const changed=resetForStatus(state,action.status);
   const updated={...state,status:action.status,live:changed?liveForStatus(action.status,state.selectedSeries):rebased(state.live,action.status),zoom:changed?initialZoom:state.zoom,catalog:changed?{...state.catalog,variables:null,registers:null}:state.catalog,transport:{...state.transport,stale:changed||state.transport.stale,needsStatusRefresh:guarded?false:state.transport.needsStatusRefresh},notices:changed?resetNotice(state,"Live view reset for a new binding or run"):state.notices};
   const prior=state.status!==null&&catalogBindingKey(state.status)!==catalogBindingKey(action.status)?retireScopes(updated,catalogScopes):updated;
   return state.status!==null&&sourceContextKey(state.status)!==sourceContextKey(action.status)?retireSource(prior):prior;
  }
 if(action.type==="probes.loaded")return {...state,probes:action.probes};
 if(action.type==="groups.loaded"){
  const selected=state.selectedGroupId===null?null:action.groups.find(group=>group.groupId===state.selectedGroupId)??null;
  const sourceId=state.groupDraft.sourceGroupId;
  const source=sourceId===null?null:action.groups.find(group=>group.groupId===sourceId)??null;
  const dirty=groupDirty(state);
  const draft=sourceId!==null&&!dirty?(source===null?emptyDraft:draftFromGroup(source)):state.groupDraft;
  return withoutConflictFailures({...state,groups:action.groups,groupsNeedRefresh:false,selectedGroupId:selected?.groupId??null,groupDraft:draft,
    groupBaseline:sourceId!==null&&!dirty?draft:state.groupBaseline,
    groupGeneration:sourceId!==null&&!dirty?state.groupGeneration+1n:state.groupGeneration});
 }
 if(action.type==="group.acknowledged"){
  const existing=state.groups.findIndex(group=>group.groupId===action.group.groupId);
  const groups=existing<0?[...state.groups,action.group]:state.groups.map(group=>group.groupId===action.group.groupId?action.group:group);
  if(state.groupGeneration!==action.generation)return {...state,groups};
  const canonical=draftFromGroup(action.group);
  const draft=sameDraft(state.groupDraft,action.submittedDraft)?canonical:
    {...state.groupDraft,sourceGroupId:action.group.groupId,expectedRevision:action.group.revision};
  return withoutConflictFailures({...state,groups,selectedGroupId:action.group.groupId,groupDraft:draft,groupBaseline:canonical,groupNameReviewRequired:false});
 }
 if(action.type==="group.deleted"){
  const groups=state.groups.filter(group=>group.groupId!==action.groupId);
  const editing=state.groupDraft.sourceGroupId===action.groupId;
  return withoutConflictFailures({...state,groups,selectedGroupId:state.selectedGroupId===action.groupId?null:state.selectedGroupId,
    groupDraft:editing?emptyDraft:state.groupDraft,groupBaseline:editing?emptyDraft:state.groupBaseline,
    groupGeneration:editing?state.groupGeneration+1n:state.groupGeneration,groupNavigation:null,
    groupNameReviewRequired:editing?false:state.groupNameReviewRequired});
 }
 if(action.type==="groups.imported"){
  const accepted=new Map(action.groups.map(group=>[group.groupId,group]));
  const groups=[...state.groups.map(group=>accepted.get(group.groupId)??group),
    ...action.groups.filter(group=>!state.groups.some(prior=>prior.groupId===group.groupId))];
  return {...state,groups};
 }
 if(action.type==="source.started"){
  if(state.status===null||sourceContextKey(state.status)!==action.contextKey||
    action.generation<=state.catalog.source.generation)return state;
  return {...state,catalog:{...state.catalog,source:{query:action.query,initialized:true,
    generation:action.generation,contextKey:action.contextKey,page:null,children:{},lastAddedId:null}}};
 }
 if(action.type==="source.loaded"){
  const source=state.catalog.source,page=action.page;
  if(state.status===null||sourceContextKey(state.status)!==action.contextKey||
    source.contextKey!==action.contextKey||source.generation!==action.generation||source.query!==action.query||
    page.identity.workspaceId!==state.status.workspaceId||page.identity.sessionId!==state.status.sessionId||
    page.identity.logicalProjectId!==state.status.project.logicalProjectId||
    page.identity.targetDevice!==state.status.project.targetDevice||
    page.identity.bindingEpoch!==state.status.sampling.bindingEpoch)return state;
  const statusFirmware=state.status.firmware;
  const firmwareMatches=statusFirmware!==null&&page.identity.buildId!==null&&page.identity.elfSha256!==null&&
    page.identity.buildId===statusFirmware.buildId&&page.identity.elfSha256===statusFirmware.elfSha256&&
    page.identity.sourceSnapshotSha256===statusFirmware.inputSnapshotSha256;
  const safePage=firmwareMatches?page:{...page,items:page.items.map(item=>item.canAdd?
    {...item,canAdd:false,reason:"source_mismatch" as const}:item)};
  if(action.parentId===null){
   const prior=source.page;
   if(action.cursor!==null&&(prior===null||prior.nextCursor!==action.cursor||prior.catalogId!==safePage.catalogId))return state;
   const seen=new Set(prior?.items.map(item=>item.id)??[]);
   if(action.cursor!==null&&safePage.items.some(item=>seen.has(item.id))||safePage.items.some(item=>item.parentId!==null))return state;
   const merged={...safePage,cursor:action.cursor,items:action.cursor===null?safePage.items:[...prior!.items,...safePage.items]};
   return {...state,catalog:{...state.catalog,source:{...source,page:merged,
     children:action.cursor===null?{}:source.children,lastAddedId:null}}};
  }
  const root=source.page,parent=root?.items.find(item=>item.id===action.parentId)??
    Object.values(source.children).flatMap(child=>child.items).find(item=>item.id===action.parentId);
  if(root===null||parent===undefined||!parent.expandable||root.catalogId!==safePage.catalogId||
    safePage.items.some(item=>item.parentId!==action.parentId))return state;
  const prior=source.children[action.parentId];
  if(action.cursor!==null&&(prior===undefined||prior.nextCursor!==action.cursor))return state;
  const seen=new Set(prior?.items.map(item=>item.id)??[]);
  if(action.cursor!==null&&safePage.items.some(item=>seen.has(item.id)))return state;
  const merged={...safePage,cursor:action.cursor,items:action.cursor===null?safePage.items:[...prior!.items,...safePage.items]};
  return {...state,catalog:{...state.catalog,source:{...source,children:{...source.children,[action.parentId]:merged}}}};
 }
 if(action.type==="source.selection.accepted"){
  const source=state.catalog.source;
  if(state.status===null||sourceContextKey(state.status)!==action.contextKey||
    source.contextKey!==action.contextKey||source.generation!==action.generation||
    state.groupGeneration!==action.groupGeneration||state.groupNavigation!==null||groupWorkflowBusy(state)||
    source.page?.catalogId!==action.catalogId||action.watch.kind!=="variable"||
    action.watch.expression!==action.selector)return state;
  const item=source.page.items.find(item=>item.id===action.itemId)??
    Object.values(source.children).flatMap(child=>child.items).find(item=>item.id===action.itemId);
  if(item===undefined||!item.canAdd||item.selector!==action.selector||
    state.groupDraft.items.some(watch=>watchKey(watch)===watchKey(action.watch)))return state;
  return {...state,groupDraft:{...state.groupDraft,items:[...state.groupDraft.items,action.watch]},
    catalog:{...state.catalog,source:{...source,lastAddedId:action.itemId}}};
 }
 if(action.type==="catalog.loaded"){
  if(state.status===null||catalogBindingKey(state.status)!==action.bindingKey)return state;
  if(action.catalog==="variables"){
   const prior=state.catalog.variables;
   if(action.cursor!==null&&(prior===null||prior.query!==action.query||prior.bindingKey!==action.bindingKey||prior.nextCursor!==action.cursor||prior.cursor===action.cursor))return state;
   return {...state,catalog:{...state.catalog,variables:{kind:"variables",query:action.query,bindingKey:action.bindingKey,cursor:action.cursor,items:uniqueCatalogItems(action.cursor===null?[]:prior!.items,action.items),nextCursor:action.nextCursor}}};
  }
  const prior=state.catalog.registers;
  if(action.cursor!==null&&(prior===null||prior.query!==action.query||prior.bindingKey!==action.bindingKey||prior.nextCursor!==action.cursor||prior.cursor===action.cursor))return state;
  return {...state,catalog:{...state.catalog,registers:{kind:"registers",query:action.query,bindingKey:action.bindingKey,cursor:action.cursor,items:uniqueCatalogItems(action.cursor===null?[]:prior!.items,action.items),nextCursor:action.nextCursor}}};
 }
 if(action.type==="group.selected")return reducer(state,{type:"group.navigation.requested",target:action.groupId===null?{kind:"new"}:{kind:"group",groupId:action.groupId}});
 if(action.type==="group.navigation.requested"){
  if(groupWorkflowBusy(state)||state.groupNavigation!==null)return state;
  if(action.target.kind==="group"&&action.target.groupId===state.groupDraft.sourceGroupId)return state;
  return groupDirty(state)?{...state,groupNavigation:action.target,groupNavigationMissing:false}:navigate(state,action.target);
 }
 if(action.type==="group.navigation.cancelled")return state.groupNavigation===null||groupWorkflowBusy(state)?state:{...state,groupNavigation:null,groupNavigationMissing:false};
 if(action.type==="group.navigation.confirmed")return state.groupNavigation===null||groupWorkflowBusy(state)?state:navigate(state,state.groupNavigation);
 if(action.type==="group.save-as-new"){
  if(groupWorkflowBusy(state)||state.groupNavigation!==null)return state;
  const draft={...state.groupDraft,sourceGroupId:null,expectedRevision:null,items:[...state.groupDraft.items]};
  return withoutConflictFailures({...state,selectedGroupId:null,groupDraft:draft,groupBaseline:emptyDraft,
    groupGeneration:state.groupGeneration+1n,groupNavigationMissing:false,groupNameReviewRequired:true});
 }
 if(action.type==="group.name.reviewed")return groupWorkflowBusy(state)||state.groupNavigation!==null||!state.groupNameReviewRequired
  ?state:{...state,groupNameReviewRequired:false};
 if(action.type==="group.write.started")return {...state,groupWriteBusy:true};
 if(action.type==="group.write.ended")return {...state,groupWriteBusy:false};
 if(action.type==="group.draft.changed"){
  if(groupWorkflowBusy(state)||state.groupNavigation!==null)return state;
  const draft={...state.groupDraft,name:action.draft.name,description:action.draft.description,
    intervalMs:action.draft.intervalMs,items:[...action.draft.items]};
  return sameGroupContent(draft,state.groupDraft)?state:{...state,groupDraft:draft,groupNavigationMissing:false,
    groupNameReviewRequired:action.draft.name!==state.groupDraft.name?false:state.groupNameReviewRequired};
 }
 if(action.type==="group.watch.added")return groupWorkflowBusy(state)||state.groupNavigation!==null||state.groupDraft.items.some(item=>watchKey(item)===watchKey(action.watch))?state:{...state,groupDraft:{...state.groupDraft,items:[...state.groupDraft.items,action.watch]}};
 if(action.type==="group.watch.removed"){
  if(groupWorkflowBusy(state)||state.groupNavigation!==null)return state;
  const items=state.groupDraft.items.filter(item=>watchKey(item)!==action.key);
  return items.length===state.groupDraft.items.length?state:{...state,groupDraft:{...state.groupDraft,items}};
 }
 if(action.type==="series.toggled"){const selected=new Set(state.selectedSeries);if(selected.has(action.key))selected.delete(action.key);else if(selected.size<8)selected.add(action.key);else return state;return {...state,selectedSeries:selected,live:{...state.live,selectedSeries:selected}};}
 if(action.type==="zoom.changed"){
  const zoom=zoomReducer(state.zoom,action.action);
  return zoom===state.zoom?state:{...state,zoom};
 }
 if(action.type==="zoom.reset")return state.zoom===initialZoom?state:{...state,zoom:initialZoom};
 if(action.type==="history.loaded"){
  const projection=projectHistoryPage(action.page,new Map(state.groups.map(group=>[group.groupId,group])),state.selectedSeries);
  const cursorStack=action.navigation==="next"?[...state.history.cursorStack,state.history.query?.cursor]
    :action.navigation==="previous"?state.history.cursorStack.slice(0,-1):[];
  return {...state,history:{...state.history,query:action.query,page:action.page,projection,cursorIndex:cursorStack.length,cursorStack,nextCursor:action.page.nextCursor}};
 }
 if(action.type==="export.loaded"){
  if(action.submitted!==undefined){
   if(action.submitted.exportId!==action.artifact.exportId)return state;
   const updated={...state,exports:{artifact:action.artifact,submitted:action.submitted}};
   return state.exports.artifact?.exportId!==action.artifact.exportId?retireScopes(updated,["export.status"]):updated;
  }
  if(state.exports.artifact!==null&&state.exports.artifact.exportId!==action.artifact.exportId)return state;
  return {...state,exports:{artifact:action.artifact,submitted:state.exports.submitted}};
 }
 if(action.type==="request.started"){
  const failures={...state.failures};delete failures[action.scope];
  const reconciling={...state.reconciling};delete reconciling[action.scope];
  const history=action.scope==="history"?{...state.history,inFlight:action.historyContext===undefined?null:
    {requestId:action.requestId,query:{...action.historyContext.query},navigation:action.historyContext.navigation}}:state.history;
  return {...state,pending:{...state.pending,[action.scope]:{requestId:action.requestId}},failures,reconciling,history};
 }
 if(action.type==="request.cleared"){const pending=state.pending[action.scope];if(pending===undefined||pending.requestId!==action.requestId)return state;const copy={...state.pending};delete copy[action.scope];return {...state,pending:copy,history:settledHistory(state,action.scope,action.requestId)};}
 if(action.type==="request.failed"){
  const pending=state.pending[action.scope];if(pending===undefined||pending.requestId!==action.requestId||state.blockingError!==null)return state;
  const pendingCopy={...state.pending};delete pendingCopy[action.scope];
  return {...state,pending:pendingCopy,history:settledHistory(state,action.scope,action.requestId),groupsNeedRefresh:state.groupsNeedRefresh||action.recovery==="groups-refresh",
    failures:{...state.failures,[action.scope]:{ok:false,code:action.code,message:action.message,requestId:action.requestId,recovery:action.recovery??"none",summary:action.summary??"操作"}}};
 }
  if(action.type==="transport.checking")return {...state,transport:{...state.transport,phase:"checking",open:false,stale:true}};
  if(action.type==="transport.connecting")return {...state,transport:{...state.transport,phase:"connecting",open:false,stale:true}};
  return action.type==="transport.open"?{...state,transport:{...state.transport,phase:"open",open:true}}:{...state,transport:{...state.transport,phase:"disconnected",open:false,stale:true}};
}
