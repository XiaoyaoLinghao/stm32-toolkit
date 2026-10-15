import type {ApiFailure,SamplingStatus} from "../api/contract";

/** Product copy stays here; wire codes and user data remain unchanged. */
export const copy={
  app:"STM32 监视器",loading:"正在读取监视状态…",live:"实时监视",history:"历史记录",
  device:"连接与固件详情",close:"关闭",diagnostics:"诊断详情",retryOpen:"若服务仍在运行，请先在所属 Monitor 终端按 Ctrl-C 结束，再运行 open 打开新的授权页面。",
  invalidRange:"请填写有效的 UTC 起止时间，且结束时间晚于开始时间。",
  probeConnected:"探针已连接",probeDisconnected:"探针未连接",mainNav:"主导航",watchConfig:"观测对象配置",
  samplingServerLabel:"设备采样状态：",streamLost:"数据连接中断 · 等待重新连接",streamConnecting:"正在连接实时数据",
  catalogBrowse:"浏览变量与寄存器",catalogCollapse:"收起变量目录",catalogTitle:"变量与寄存器目录",catalogResults:"目录搜索结果",
  catalogKind:"目录类型",variables:"变量",registers:"寄存器",search:"搜索",
  searchPlaceholder:"输入符号或寄存器前缀",catalogNeedsProbe:"连接探针后可搜索目录。",
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
  name:"名称",description:"描述",interval:"采样间隔（ms）",watch:"观测对象",remove:"移除",
  groupCreate:"创建观测组",groupSave:"保存观测组",importJsonInvalid:"导入文件不是有效的 JSON。",
  importReadFailed:"无法读取导入文件，请重新选择。",
  historyTitle:"历史查询",historyHint:"起止时间均按 UTC 解释；查询不会自动覆盖全部历史。",
  historyStart:"开始时间（UTC）",historyEnd:"结束时间（UTC）",historyLoad:"查询历史",
  historyChoose:"请选择 UTC 起止时间后查询历史记录。",historyEmpty:"此范围内暂无历史记录。",
  historyCaptured:"采集时间（UTC）",value:"数值",readFailed:"读取失败",previousPage:"上一页",
  identityTitle:"项目与固件身份",logicalProject:"逻辑项目：",targetDevice:"目标芯片：",
  noFirmware:"尚无已验证的固件身份。",firmwareBuild:"固件构建：",elfLabel:"ELF：",gitLabel:"Git：",gitDirty:"有未提交改动",copyIdentity:"复制工作区身份",
  chartTitle:"实时波形",chartLimit:"最多显示 8 条曲线",chartAria:"实时数值波形图",
  chartEmpty:"选择观测组及曲线后显示波形。",valuesTitle:"最新数值",valuesStale:"非最新数据",
  trend:"趋势",curve:"曲线",curveShow:"显示",curveHide:"隐藏",
  valuesEmpty:"当前观测组暂无最新数值。请选择观测对象并开始采样。",
  notices:"监视通知",probeTitle:"探针连接",probeRefresh:"刷新探针列表",
  probeNone:"未检测到探针。请检查连接后刷新列表。",probeOnline:"（已连接）",probeConnect:"连接",
  probeReConnect:"重新连接",probeRelease:"释放探针",probeConnectedPrefix:"已连接：",
  samplingControls:"采样控制",samplingTitle:"实时采样",samplingBlocked:" · 已受阻",
  samplingGroup:"观测组：",samplingNoGroup:"尚未选择",samplingStart:"开始采样",samplingPause:"暂停采样",
  samplingResume:"继续采样",samplingStop:"停止采样",statusSummary:"采样状态汇总",
  actualRate:"实际采样率",latency:"延迟",rawNs:"原始纳秒值",dropsSubscriber:"丢弃：订阅者",
  dropsHistory:"历史",dropsDeadline:"截止时间",dropsService:"服务",blockedOperation:"当前操作未完成。",
} as const;

export const formatCopy={
  bits:(count:number)=>`${count} 位`,
  groupDelete:(name:string)=>`确定删除 ${name}？`,
  importPreview:(groups:number,items:number)=>`将导入 ${groups} 个观测组、${items} 个观测对象。确认继续？`,
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
  MONITOR_BOOTSTRAP_SERVICE_FAILED:{title:"监视器启动失败",action:copy.retryOpen},
  MONITOR_BOOTSTRAP_RESPONSE_INVALID:{title:"启动响应无效",action:copy.retryOpen},
  MONITOR_BOOTSTRAP_REQUEST_FAILED:{title:"启动请求未完成",action:copy.retryOpen},
  MONITOR_IMPORT_INVALID:{title:"导入文件无效",action:"检查 JSON 文件内容后重新选择文件。"},
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
