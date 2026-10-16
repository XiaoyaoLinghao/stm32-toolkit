import type {ApiFailure,SamplingStatus} from "../api/contract";
import type {RequestScope,RecoveryKind} from "../state/model";

/** Product copy stays here; wire codes and user data remain unchanged. */
export const copy={
  app:"STM32 监视器",loading:"正在读取监视状态…",live:"实时监视",history:"历史记录",
  device:"连接与固件详情",close:"关闭",diagnostics:"诊断详情",retryOpen:"若服务仍在运行，请先在所属 Monitor 终端按 Ctrl-C 结束，再运行 open 打开新的授权页面。",
  invalidRange:"请填写有效的 UTC 起止时间，且结束时间晚于开始时间。",
  historyInvalidRange:"请填写有效的 UTC 起止时间：起点不得早于 1970 年，终点须晚于起点且不超过可查询范围。",
  probeConnected:"探针已连接",probeDisconnected:"探针未连接",mainNav:"主导航",watchConfig:"观测对象配置",
  samplingServerLabel:"设备采样状态：",streamLost:"数据连接中断 · 等待重新连接",streamConnecting:"正在连接实时数据",
  streamChecking:"正在核对监视会话",streamConnected:"实时数据已连接",streamStale:"非最新数据",
  liveReconnect:"重新连接实时数据",liveCancel:"取消连接",statusRefreshNeeded:"需要刷新状态",statusRefresh:"刷新状态",
  catalogBrowse:"浏览变量与寄存器",catalogCollapse:"收起变量目录",catalogTitle:"变量与寄存器目录",catalogResults:"目录搜索结果",
  catalogKind:"目录类型",variables:"变量",registers:"寄存器",search:"搜索",
  searchPlaceholder:"输入符号或寄存器前缀",catalogLoad:"搜索/加载",catalogNeedsProbe:"连接探针后可搜索目录。",
  catalogMore:"；还有更多结果，可加载下一页。",
  registerAccessAcknowledgement:"该寄存器需要现有访问能力确认；添加草稿不会自动授权。",
  selector:"选择器",type:"类型",action:"操作",addDraft:"加入观测组草稿",nextPage:"下一页",
  zoomTitle:"图表缩放",zoomRange:"显示范围：",zoomIn:"放大",zoomOut:"缩小",zoomReset:"重置缩放",
  exportRegion:"历史导出",exportTitle:"导出历史记录",exportHint:"使用已提交查询范围，或手动指定独立的 UTC 范围。",
  exportStart:"导出开始时间（UTC）",exportEnd:"导出结束时间（UTC）",
  exportRetained:"查询范围已更新，保留当前导出范围。",exportUseQuery:"使用查询范围",
  exportCsv:"创建 CSV 导出",exportJsonl:"创建 JSONL 导出",exportConfirmTitle:"确认历史导出",
  exportConfirm:"确认导出",cancel:"取消",exportRefresh:"刷新导出状态",exportDownload:"下载已验证的 ",
  exportSubmitting:"正在创建导出任务…",exportRefreshing:"正在刷新导出状态…",
  groupTitle:"观测组",groupDelete:"删除",groupConfirmDelete:"确认删除",groupNone:"暂无观测组。新建并添加观测对象后即可采样。",
  groupNew:"新建观测组",groupCollapse:"收起组配置",groupEdit:"编辑组配置",groupExport:"导出观测组 JSON",
  groupImport:"导入观测组",groupFile:"选择观测组 JSON 文件",groupConfirmImport:"确认导入",
  groupNewDraft:"新建观测组草稿",groupEditDraft:"编辑观测组草稿",groupDraftHint:"草稿需要保存后才会用于采样。",
  groupUnsaved:"未保存；下次采样尚无此目标。",groupDirty:"有未保存的修改",
  groupRefresh:"刷新观测组",groupUnsavedTitle:"未保存的观测组修改",
  groupUnsavedQuestion:"切换会放弃当前未保存的修改。",groupKeepEditing:"继续编辑",groupDiscardContinue:"放弃修改并继续",
  groupNavigationMissing:"目标观测组已不在列表中；原草稿仍保留。请刷新或重新选择。",
  groupSourceDeleted:"原组已删除。当前草稿已保留；不能向原组保存。",
  groupSourceChanged:"原组版本已变化。当前草稿已保留；请重新载入或另存。",
  groupReloadLatest:"放弃草稿并载入最新版本",groupSaveAsNew:"保留为新组",
  groupReviewName:"请检查新组名称；名称冲突仍以服务端核对为准。",groupConfirmName:"确认使用此名称",
  groupImportItems:"个对象",groupImportNoOverwrite:"导入不会覆盖已有组；名称冲突由服务端检查，失败时保留当前草稿。",
  name:"名称",description:"描述",interval:"采样间隔（ms）",watch:"观测对象",remove:"移除",
  groupCreate:"创建观测组",groupSave:"保存观测组",importReading:"正在读取导入文件…",importJsonInvalid:"导入文件不是有效的 JSON。",
  importReadFailed:"无法读取导入文件，请重新选择。",
  historyTitle:"历史查询",historyHint:"起止时间均按 UTC 解释；查询不会自动覆盖全部历史。",
  historyStart:"开始时间（UTC）",historyEnd:"结束时间（UTC）",historyLoad:"查询历史",
  historyChoose:"请选择 UTC 起止时间后查询历史记录。",historyEmpty:"此范围内暂无历史记录。",
  historyPendingRange:"正在查询范围（UTC）",historyCurrentRange:"当前结果范围（UTC）",historyHalfOpen:"起点包含，终点不含",
  historyPreviousResult:"查询期间仍显示上次成功结果。",historySource:"来源",historyRun:"轮次",historySequence:"序号",historyOrdinal:"值序位",
  historyCaptured:"采集时间（UTC）",value:"数值",readFailed:"读取失败",previousPage:"上一页",
  identityTitle:"项目与固件身份",logicalProject:"逻辑项目：",targetDevice:"目标芯片：",
  noFirmware:"尚无已验证的固件身份。",firmwareBuild:"固件构建：",elfLabel:"ELF：",gitLabel:"Git：",gitDirty:"有未提交改动",copyIdentity:"复制工作区身份",
  chartTitle:"实时波形",chartLimit:"最多显示 8 条曲线",chartAria:"实时数值波形图",
  chartTimeAxis:"相对时间（ms）",chartOrigin:"起点（UTC）：",chartMissingValue:"读取空缺",
  chartEmpty:"选择曲线后显示波形。",chartWaiting:"已选择曲线，等待采样数据。",
  chartNoValues:"已有采集时间，但暂无可绘制的数值。",valuesTitle:"最新数值",valuesStale:"非最新数据",
  trend:"趋势",curve:"曲线",curveShow:"显示曲线",curveHide:"隐藏曲线",
  selectedCurves:"已选曲线",removeCurve:"移除曲线",curveLimitReached:"最多只能选择 8 条曲线；先移除已选曲线。",
  valuesEmpty:"当前观测组暂无最新数值。请选择观测对象并开始采样。",
  liveSource:"采样数据来源",liveSourcePreview:"下次目标预览；尚未开始采样。",liveSourceAwaiting:"当前采样轮次；等待本轮样本",
  liveSourceCurrent:"当前采样轮次",liveSourcePrevious:"上次样本轮次",liveSourceGroup:"运行组",liveSourceRevision:"版本",
  liveSourceUnverified:"运行组版本未在列表中核对，仅展示上次样本。",liveSourceUnverifiedEmpty:"运行组版本未在列表中核对；尚未收到样本。",
  notices:"监视通知",probeTitle:"探针连接",probeRefresh:"刷新探针列表",
  probeNone:"未检测到探针。请检查连接后刷新列表。",probeOnline:"（已连接）",probeConnect:"连接",
  probeReConnect:"重新连接",probeRelease:"释放探针",probeConnectedPrefix:"已连接：",
  samplingControls:"采样控制",samplingTitle:"实时采样",samplingBlocked:" · 已受阻",
  samplingGroup:"下次开始采样：",samplingActiveGroup:"当前运行：",samplingNoGroup:"尚未选择",samplingStart:"开始采样",samplingPause:"暂停采样",
  samplingResume:"继续采样",samplingStop:"停止采样",statusSummary:"采样状态汇总",
  actualRate:"实际采样率",latency:"延迟",rawNs:"原始纳秒值",noSampleYet:"尚未收到样本",lastSample:"上次样本（UTC）",dropsSubscriber:"丢弃：订阅者",
  dropsHistory:"历史",dropsDeadline:"截止时间",dropsService:"服务",blockedOperation:"当前操作未完成。",
  operations:"操作提示",retry:"重试上次操作",reconcile:"刷新核对",retryConfirm:"确认重试上次写入",
  retryQuestion:"将按原提交内容再次发送此操作。请确认：",initialRetry:"重试初始化",
  previousCatalog:"显示上次成功的查询结果；当前搜索尚未成功。",
  pendingOperation:"正在处理…",unknownWrite:"写入结果未知。刷新只能核对当前状态，不能证明原操作成功。",
  unknownExport:"导出创建结果未知，无法查询未知任务。可保留当前表单并自行发起新的导出。",
  chooseImportAgain:"请检查导入文件内容或数量，再重新选择文件。",
  groupConflictRefresh:"服务端未接受这次组操作。刷新观测组列表以核对版本和名称；草稿会保留，刷新不会重发写入。",
  groupInputCorrect:"请修改草稿或观测对象后重新提交。",
  requestInputCorrect:"请检查当前操作的输入后重新提交。",
} as const;

const operationNames:Record<RequestScope,string>={
  initial:"初始化读取",status:"状态刷新","live.reconnect":"重新连接实时数据",probes:"探针列表刷新",
  "probe.connect":"连接探针","probe.reconnect":"重新连接探针","probe.release":"释放探针",
  "catalog.variables":"变量目录搜索","catalog.registers":"寄存器目录搜索",
  "groups.list":"观测组列表刷新","groups.create":"创建观测组","groups.update":"保存观测组",
  "groups.delete":"删除观测组","groups.import":"导入观测组",
  "sampling.start":"开始采样","sampling.pause":"暂停采样","sampling.resume":"继续采样",
  "sampling.stop":"停止采样",history:"历史查询","export.create":"创建导出",
  "export.status":"导出状态刷新","export.download":"导出下载",
};
const utcNs=(value:string):string=>{
  try{return new Date(Number(BigInt(value)/1_000_000n)).toISOString();}
  catch{return value+" ns";}
};
export function operationSummary(scope:RequestScope,...details:(string|undefined)[]):string{
  const name=operationNames[scope];
  if(scope==="export.create")return name+" · "+(details[0]??"").toUpperCase()+" · "+utcNs(details[1]??"0")+" 至 "+utcNs(details[2]??"0");
  if(scope==="history")return name+" · "+utcNs(details[0]??"0")+" 至 "+utcNs(details[1]??"0")+(details[2]===undefined?"":" · 翻页");
  if(scope==="catalog.variables"||scope==="catalog.registers")return name+" · "+(details[0]??"")+(details[1]===undefined?"":" · 下一页");
  if(scope==="groups.import")return name+" · "+(details[0]??"0")+" 组";
  if(scope==="probe.reconnect"||scope==="probe.release")return name+" · 探针 "+(details[0]??"未知");
  if(scope==="sampling.start")return name+" · 观测组 "+(details[0]??"未知")+" · 探针 "+(details[1]??"未知")+" · 轮次 "+(details[2]??"未开始");
  if(scope==="sampling.pause"||scope==="sampling.resume"||scope==="sampling.stop")
    return name+" · 观测组 "+(details[0]??"未知")+" · 轮次 "+(details[1]??"未知")+" · 探针 "+(details[2]??"未知");
  const extra=details.filter((item):item is string=>item!==undefined&&item!=="");
  return extra.length===0?name:name+" · "+extra.join(" · ");
}
export function recoveryText(recovery:RecoveryKind,scope:RequestScope):string{
  if(recovery==="read-retry")return scope==="initial"?copy.initialRetry:copy.retry;
  if(recovery==="write-confirm")return copy.retry;
  if(recovery==="reconcile")return copy.unknownWrite+" "+copy.reconcile;
  if(recovery==="groups-refresh")return copy.groupConflictRefresh;
  if(recovery==="input")return scope==="groups.import"?copy.chooseImportAgain:
    scope==="groups.create"||scope==="groups.update"||scope==="groups.delete"?copy.groupInputCorrect:copy.requestInputCorrect;
  return scope==="export.create"?copy.unknownExport:copy.unknownWrite;
}
export function recoveryAction(recovery:RecoveryKind,scope:RequestScope):string{
  return recovery==="groups-refresh"?copy.groupRefresh:recovery==="reconcile"?copy.reconcile:scope==="initial"?copy.initialRetry:copy.retry;
}

export const formatCopy={
  catalogLoaded:(count:number)=>`已加载 ${count} 项`,
  selectedCount:(count:number)=>`已选择 ${count} / 8 条曲线`,
  bits:(count:number)=>`${count} 位`,
  groupDelete:(name:string)=>`确定删除 ${name}？`,
  importPreview:(groups:number,items:number)=>`将导入 ${groups} 个观测组、${items} 个观测对象。确认继续？`,
  registerUnavailable:(access:string|null,readAction:string|null)=>`不可采样（access: ${access??"未知"}；readAction: ${readAction??"未知"}）。`,
  exportQuestion:(format:string)=>`将当前会话中所选时间范围导出为 ${format}？`,
  artifactSummary:(bytes:bigint,count:bigint)=>`已生成：${bytes} 字节 · ${count} 个数值`,
  submittedRange:(start:string,end:string)=>`提交时范围（UTC）：${start} 至 ${end}`,
};

const states:Record<SamplingStatus["state"],string>={
  IDLE:"未采样",STARTING:"正在启动",RUNNING:"采样中",PAUSED:"已暂停",
  PAUSED_BLOCKED:"采样受阻",STOPPING:"正在停止",
};
export function samplingState(value:string):string{return states[value as SamplingStatus["state"]]??"状态未知";}

const knownErrors:Record<string,{title:string;action:string}>={
  MONITOR_ACCESS_LINK_INVALID:{title:"授权链接无效",action:copy.retryOpen},
  MONITOR_ACCESS_REJECTED:{title:"授权链接被拒绝",action:copy.retryOpen},
  MONITOR_SESSION_EXPIRED:{title:"当前会话已失效",action:"如果服务仍在运行，先在启动终端按 Ctrl+C 停止，再用相同 open ... --port ... 命令重新启动并自动认证。"},
  MONITOR_BOOTSTRAP_SERVICE_FAILED:{title:"监视器启动失败",action:copy.retryOpen},
  MONITOR_BOOTSTRAP_RESPONSE_INVALID:{title:"启动响应无效",action:copy.retryOpen},
  MONITOR_BOOTSTRAP_REQUEST_FAILED:{title:"启动请求未完成",action:copy.retryOpen},
  MONITOR_IMPORT_INVALID:{title:"导入文件无效",action:"检查 JSON 文件内容后重新选择文件。"},
  MONITOR_GROUP_CONFLICT:{title:"观测组冲突",action:copy.groupConflictRefresh},
  MONITOR_GROUP_NOT_FOUND:{title:"观测组不存在",action:copy.groupConflictRefresh},
  MONITOR_IMPORT_CONFLICT:{title:"导入名称冲突",action:copy.groupConflictRefresh},
  MONITOR_REQUEST_INVALID:{title:"请求无效",action:copy.requestInputCorrect},
  MONITOR_GROUP_LIMIT_EXCEEDED:{title:"观测组或对象数量超限",action:copy.groupInputCorrect},
};
export function errorText(code:string):{title:string;action:string}{
  return knownErrors[code]??{title:"操作未完成",action:"请查看详细信息。"};
}
export function failureText(failure:ApiFailure):{title:string;action:string}{return errorText(failure.code);}

const knownNotices:Record<string,string>={
  "Live view reset for a new binding or run":"连接身份或采样轮次已变化，实时视图已重置。",
  "Live event gap; status refresh required":"实时数据出现间断，正在等待状态刷新。",
};
export function noticeText(value:string):string{return knownNotices[value]??"监视状态已变化，请查看详情。";}

function scaled(value:bigint,unit:bigint):string{
  const whole=value/unit;
  const fraction=(value%unit)*100n/unit;
  return `${whole}.${fraction.toString().padStart(2,"0")}`;
}
export function latencyText(value:bigint):string{
  const magnitude=value<0n?-value:value;
  const sign=value<0n?"-":"";
  if(magnitude<1000n)return `${value} ns`;
  if(magnitude<1_000_000n)return `${sign}${scaled(magnitude,1000n)} μs`;
  if(magnitude<1_000_000_000n)return `${sign}${scaled(magnitude,1_000_000n)} ms`;
  return `${sign}${scaled(magnitude,1_000_000_000n)} s`;
}
export function trendText(value:string):string{
  return ({up:"上升",down:"下降",flat:"持平",stable:"持平",none:"无趋势"} as Record<string,string>)[value]??"未知趋势";
}
