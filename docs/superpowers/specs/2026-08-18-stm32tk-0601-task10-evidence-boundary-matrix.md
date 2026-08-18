# STM32TK-0601 T10.1 冻结边界矩阵

日期：2026-08-18
审查对象：规范与矩阵，不是候选代码
规范基线：docs-only correction parent `9db31c12711c1bac40a43a7fbf8427f9aaa93c86`；冻结审计候选 `ee2b153e031e45710cd7da5e60b00757678da07c` 仅作诊断来源，不是实现父提交

## 1. 规范标签与分类

- `S6.1`：Task 10 spec 的四类 Evidence typed error 与独立 `GcStoreChangedError`。
- `S7`：固定安全公共 message/details；禁止绝对路径、`str(exc)` 和 exception text。
- `S9`：T10.1 交付面与 allowed paths。
- `B15`：T10.1 brief 的 INVALID/CORRUPT/PATH_UNSAFE/LIMIT 与 GC phase 优先级。
- `B136`：命名 fault/publication seam 保留语义。

分类：A=当前规范且有精确测试；B=当前规范、可执行但存在缺陷/测试缺口；C=平台专属，需对应 owner 原生证据；D=后续独立单元；E=理论加固或明确保留的 raw seam，不阻塞。

固定安全投影：

| typed code | 固定公共 message | details |
|---|---|---|
| `EVIDENCE_INVALID` | `Evidence is invalid.` | `{}` |
| `EVIDENCE_CORRUPT` | `Evidence is corrupt.` | `{}` |
| `EVIDENCE_PATH_UNSAFE` | `Evidence path is unsafe.` | `{}` |
| `EVIDENCE_LIMIT_EXCEEDED` | `Evidence limit exceeded.` | `{}` |
| `GC_STORE_CHANGED` | `Evidence store changed.` | `{}` |
| `GC_DELETE_FAILED` | `Evidence deletion failed.` | `{}` |
| `GC_PARTIAL_DELETE` | `Evidence deletion was partial.` | `{}` |

T10.1 只冻结 typed source boundary；公共 OperationResult 投影属于后续 workflow 单元（D）。

## 2. 通用状态链

所有 Store/Catalog/GC 权威读取按同一阶段编号审计：

| 阶段 | 动作 | 必须证明 |
|---|---|---|
| O0 | validate caller grammar / managed path | caller 合法、闭合 schema、路径在权威根内 |
| O1 | initial stat/lstat | regular、link/reparse/nlink、size/mtime、dev/ino/Windows file ID |
| O2 | open | 打开的是已观察对象；missing/permission 分类不泄漏路径 |
| O3 | fstat/handle info | O1 与 handle 身份/类型/link/size 状态一致 |
| O4 | read/query/hash | 有界读取；SQLite consumer 与被验证 authority 一致 |
| O5 | exact EOF | consumed bytes == opened size，且无额外字节 |
| O6 | post-stat/handle info | 读取期间 identity/link/size/mtime 未改变 |
| O7 | path/content recheck | pathname 仍指向同对象；内容摘要/SQLite状态仍绑定 |
| O8 | close/unlock/cleanup | 必须尝试；primary error 优先；cleanup-only 固定 typed/path-free |

通用故障维度：`missing`、`permission`、`malformed`、`identity drift`、`size/content drift`、`limit`、`cleanup failure`，并与 `primary success/error` 交叉。静态 unsafe 与动态 drift 不得混淆；动态 drift 的优先级高于随后发生的普通 I/O failure。

## 3. helper × caller 调用图

本节开头三张表仅作导航，不用于验收；后面的 `S01–S11/C01–C10/G01–G11` 才是规范性、可机械对账 inventory。

### Store helper

| helper | callers |
|---|---|
| `_validate_existing_path` | `_ensure_root`, `_managed_directory`, `_mutation_lock`, stable-read error/recheck, `_hash_file`, `_atomic_create_new`, source second pass, envelope put/get；Catalog root/main/aux/manifest/rebuild；GC parent/store/root/ledger |
| `_reject_casefold_collision` | managed directory/object/manifest/root/catalog query/rebuild |
| `_ensure_root` | managed directory、mutation lock、GC store identity |
| `_managed_directory` | objects、manifests、roots、Catalog scan、authorization ledger |
| `_mutation_lock` | ingest、put envelope、catalog rebuild、put_root、plan_gc、ledger、registered/reconstructed apply |
| `_open_stable_read` | stable bytes、Catalog query |
| `_finish_stable_read` | stable bytes、Catalog query header/SQLite/post-query |
| `_revalidate_stable_path` | finish stable read、hash、source second pass |
| `_read_stable_bytes` | get_envelope、put_root existing record |
| `_hash_file` | artifact verify、source first pass、object verify、GC snapshot |
| `_atomic_create_new` | mutation lock、manifest、root、ledger |
| `_expected_object` / `_verify_artifact` | ingest、envelope verification |

### Catalog caller chain

`query → bound path → root/main/casefold/aux validation → stable open/header → SQLite connect/database_list/journal/query → post aux/main recheck → SQLite close → descriptor close → summaries`。

`rebuild → mutation lock → manifest enumeration → Store.get_envelope → temp SQLite build/commit/fsync → target validation → atomic replace/fsync/final validation`。

### GC caller chain

`plan_gc → mutation lock → store identity → snapshot(entries/file identity/hash) → scan roots/manifests/objects → second snapshot → prepared plan`。

`apply_gc → registered/reconstructed → authorization/ledger/stable parent → pre-lock identity → mutation lock → plan/auth validation → initial/per-target/final snapshot → identity-bound delete → close/fsync → exact result`。

### 可机械对账的 exact callable / exit inventory

下表是矩阵的唯一 caller inventory；集合行只能引用这些 ID。数量用文档中列出的 exact helper names 分别执行 `rg -n`，并用 AST Call inventory 对账。

| ID | exact callable / exit | direct consumers / exits | 适用 O-stage |
|---|---|---|---|
| S01 | `store.py:_validate_existing_path` | current 23 direct sites；exact enclosing callers：store `_ensure_root(1),_managed_directory(1),_mutation_lock(1),validate_lock_identity(1),_raise_stable_read_error(1),_revalidate_stable_path(1),_hash_file(1),_atomic_create_new(1),_ingest_file_locked(1),_put_envelope_locked(1),get_envelope(1)`；catalog `_reject_auxiliary_state(1),query(2),_manifest_names(1),_rebuild_catalog_locked(2)`；gc `_existing_store_identity(1),put_root(2),_stable_parent_guard(1),_consume_authorization(2)` | O1/O7；O4/O5 N/A |
| S02 | `store.py:_open_readonly` | current 3 sites：`_open_stable_read(1),_hash_file(1),_ingest_file_locked(1)` | O2 |
| S03 | `store.py:_raise_stable_read_error` | current 7 sites：`_open_stable_read(2),_finish_stable_read(1),_hash_file(4)`（同一caller含不同exit） | exception exit；O5 N/A |
| S04 | `store.py:_open_stable_read` | current 2 sites：`_read_stable_bytes(1),catalog.query(1)` | O1–O3 |
| S05 | `store.py:_finish_stable_read` | current 6 sites：`_read_stable_bytes(2),catalog.query(4)` | O6–O7 |
| S06 | `store.py:_read_stable_bytes` | current 2 sites：`store.get_envelope(1),gc.put_root(1)` | O1–O8 |
| S07 | `store.py:_hash_file` | current 4 sites：`_ingest_file_locked source-first(1),_ingest_file_locked published-object(1),_verify_artifact(1),gc._snapshot_entries(1)` | O1–O8 |
| S08 | `store.py:_ingest_file_locked::source_second_pass` | current 1 loop/descriptor consumer | O1–O8；publication后 N/A |
| S09 | `store.py:_mutation_lock` | current 9 sites：`store.ingest_file(1),put_envelope(1),put_envelope_before_deadline(1); catalog.rebuild_catalog(1); gc.put_root(1),plan_gc(1),_consume_authorization(1),_apply_registered(1),_apply_reconstructed(1)` | acquire O1–O3、body、release O8；O4–O7 N/A |
| S10 | `store.py:_atomic_create_new` | direct owner exits：mutation-lock file、manifest、root、ledger各1语义caller | publication seam；O0–O8 N/A |
| S11 | `store.py:_flush_directory` | current 4 sites：`_atomic_create_new(1),_ingest_file_locked(1),catalog._rebuild_catalog_locked(1),gc._delete_identity_bound(1)` | durability seam；O0–O8 N/A |
| C01 | `catalog.py:EvidenceCatalog._bound_path` | current 2 sites：`query(1),rebuild_catalog(1)` | O0–O1 |
| C02 | `catalog.py:_reject_auxiliary_state` | current 2 sites：`query pre-connect(1),query post-query(1)` | O1/O7；O4/O5 N/A |
| C03 | `catalog.py:query::journal_header` | exact exits：`lseek-to-18(1),read-2(1),lseek-reset(1)` | O4；O5=exact 2 bytes |
| C04 | `catalog.py:query::sqlite_consumer` | exact exits：`connect(1),database_list(1),main-stat/identity(1),journal_mode(1),SELECT/fetch(1)`；不含row projection | O4；Store EOF N/A |
| C05 | `catalog.py:query::sqlite_close` | SQLite connection cleanup 1 | O8 |
| C06 | `catalog.py:query::descriptor_close` | pinned descriptor cleanup 1 | O8 |
| C07 | `catalog.py:query::row_projection` | cleanup后 `EvidenceSummary` projection 1 | post-O8；O0–O8 N/A |
| C08 | `catalog.py:_manifest_names` | current 1 site：`_rebuild_catalog_locked(1)`；内部parent iterdir/entry validate exits | O1/O7；O2–O6 N/A |
| C09 | `catalog.py:_rebuild_catalog_locked::manifest_read` | current chain `_manifest_names → store.get_envelope`，每manifest 1次 | 由S06承担 |
| C10 | `catalog.py:_rebuild_catalog_locked::publication` | temp DB commit/fsync/replace/final validate各1语义exit | publication seam；O0–O8 N/A |
| G01 | `gc.py:_stable_parent_guard` | current 1 site：`_consume_authorization(1)` | O1–O3/O7/O8；O4–O6 N/A |
| G02 | `gc.py:_file_identity_fields` | current 1 site：`_snapshot_entries(1)` | O1–O3/O8；bytes委托S07 |
| G03 | `gc.py:_snapshot_entries` | current 6 sites：`_plan_gc_locked first(1),second(1); _apply_gc_locked initial(1),per-target(1),final(1); _delete_identity_bound excluded(1)` | directory O1/O7；文件内容委托G02/S07；directory EOF N/A |
| G04 | `gc.py:_existing_store_identity` | current 5 direct sites：`_store_identity(1),_apply_registered pre-lock(1),_apply_registered locked(1),_apply_reconstructed pre-lock(1),_apply_reconstructed locked(1)` | O1/O7；O2–O6 N/A |
| G05 | `gc.py:_store_identity` | current 2 direct sites：`_plan_gc_locked(1),_apply_gc_locked initial(1)` | O1/O7；O2–O6 N/A |
| G06 | `gc.py:put_root` | public entry，current direct internal callers=`0`；内部calls S09(1),S01(2),S06(1),S10 root publication(1) | existing read O1–O8；publication N/A |
| G07 | `gc.py:_consume_authorization` | current 2 direct callers：`_apply_registered(1),_apply_reconstructed(1)`；内部calls G01(1)+ledger S09(1)/S10(1)+S01(2) | authorization commit；O4–O6 N/A |
| G08 | `gc.py:_delete_identity_bound` | current 1 site：`_apply_gc_locked(1)` | Win handle O2/O3；read/digest O4/O5/O6；G03 O7；close O8 |
| G09 | `gc.py:_apply_gc_locked` | current 1 direct caller：`_apply_registered(1)`；内部calls G03 initial/per-target/final各1 + G08(1) | orchestration；自身O0–O8 N/A |
| G10 | `gc.py:_apply_registered` | current 1 direct caller：`apply_gc(1)`；内部chain G07→G04→S09→G09→result mapping | orchestration/outer cleanup；自身O0–O8 N/A |
| G11 | `gc.py:_apply_reconstructed` | current 1 direct caller：`apply_gc(1)`；内部chain G05→S09→regenerated plan→invalid result | orchestration；自身O0–O8 N/A |

机械验收必须把这些 ID 与源码 direct sites 对账；任一新增 caller 未进入矩阵即专项审查失败。

Direct-site count 对账（accepted/current；`—`表示exit family或loop而非函数Call）：S01=`21/23`，S02=`3/3`，S03=`0/7`，S04=`0/2`，S05=`0/6`，S06=`0/2`，S07=`4/4`，S08=`—/—`，S09=`9/9`，S10=`4/4`，S11=`4/4`，C01=`2/2`，C02=`0/2`，C03–C07=`—/—`，C08=`1/1`，C09–C10=`—/—`，G01=`1/1`，G02=`1/1`，G03=`6/6`，G04=`5/5`，G05=`2/2`，G06=`0/0`，G07=`2/2`，G08=`1/1`，G09=`1/1`，G10=`1/1`，G11=`1/1`。每个单元专项审查重新生成这行；任何未解释的count变化即FAIL。

## 4. Store stable-read / source / cleanup 矩阵

| caller/格 | 阶段 | 失败状态 | 规范 | 可执行 | 预期 typed code | 已有测试 | 范围/类 |
|---|---|---|---|---:|---|---|---|
| S07/source-first | O0–O7 | missing/permission/malformed/EOF；无drift | S6.1/B15 | 是 | `INVALID` | source first-pass nodes | 1d/A |
| S08/source-second | O1–O7 | missing/permission/EOF；无确认drift | S6.1/B15 | 是 | `INVALID` | source second-pass nodes | 1d/A |
| S07/source-first或S08 | O1–O7 | same-inode size/mtime/content或path/link/identity drift | B15 | 是 | `PATH_UNSAFE` | mutation/swap nodes | 1d/A |
| S06/get_envelope | O0 | manifest identity从未存在 | B15 | 是 | `INVALID` | fixed-message node | 1c/A |
| S06/get_envelope | O1–O7 | manifest/object ordinary missing/permission/malformed/EOF | B15/S6.1 | 是 | manifest/object managed=`CORRUPT`；初始未知identity除外 | manifest/object matrix | 1c/A |
| S06/get_envelope | O1–O7 | link/reparse/hardlink/casefold/path-handle identity drift | B15 | 是 | `PATH_UNSAFE` | swap/link matrix | 1c/A |
| S06/get_envelope | O1–O7 | same identity bytes/size/mtime contradiction | B15 | 是 | `CORRUPT` | in-place/EOF nodes | 1c/A |
| S06/put_root | O1–O7 | existing root ordinary permission/malformed/EOF | B15/S6.1 | 是 | `CORRUPT` | existing root nodes | 1g/A |
| S06/put_root | O1–O7 | existing root path/link/identity drift | B15 | 是 | `PATH_UNSAFE` | lost-create/swap nodes | 1g/A |
| S07/managed-object verify | O1–O7 | ordinary permission/EOF/content contradiction | B15/S6.1 | 是 | `CORRUPT` | object matrix | 1c/A |
| S07/managed-object verify | O1–O7 | path/link/identity drift | B15 | 是 | `PATH_UNSAFE` | object swap/link nodes | 1c/A |
| S07/GC snapshot | O1–O7 | failure | B15 | 是 | non-strict→corrupt entry+retain；strict→由1h/1k phase map | GC matrix | 1h/1k/A |
| S06/S07/S08 success controls | O4–O7 | zero/multichunk、exact EOF | stable chain | 是 | success | controls | 1c/1d/1g/A |
| S06/S07/S08 final path | O7 | permission，无drift / identity drift | S6.1/B15 | 是 | owner ordinary code；drift=`PATH_UNSAFE` | caller-specific nodes仍有缺口 | 1c/1d/1g/B |
| S06 `_read_stable_bytes` | O8 | success + close failure | S6.1/S7 | 是 | `CORRUPT`, path-free | 无精确测试；当前盘点怀疑 raw | 1c/B |
| S07 `_hash_file` | O8 | success + close failure | S6.1/S7 | 是 | source=`INVALID`; managed=`CORRUPT` | 无精确测试；当前盘点怀疑 raw | 1c/1d/B |
| S08 source second copy | O8 | success + close failure | S6.1/B15 | 是 | `INVALID`；若重新观察确认path/link/identity drift则=`PATH_UNSAFE` | 旧控制期待 raw，存在冲突 | 1d/B |
| S06/S07/S08 | O8 | typed primary + close failure | priority | 是 | primary保留且仍尝试close；若cleanup重观察确认path/link/identity drift，`PATH_UNSAFE`优先 | source部分；managed交叉不足 | 1c/1d/B |
| atomic publication/fault/fsync | publication | named fault或durability failure | B136 | 是 | 保留冻结 raw lifecycle | fault tests | E |
| bounded public read | 后续API | read_artifact | S9 | 未实现 | T10.2 contract | 无 | D |

## 5. Store mutation-lock 矩阵

| 格 | 阶段 | 状态 | 规范 | 可执行 | 预期 | 已有测试 | 类 |
|---|---|---|---|---:|---|---|---|
| S09/non-GC consumers | O1–O3 acquire | initial static unsafe | B15 | 是 | `EVIDENCE_PATH_UNSAFE` | lock matrix | 1b/A |
| S09/plan_gc | O1–O3 acquire | initial static unsafe / ordinary denial / post-observation drift | B15/S6.1 | 是 | static unsafe=`EVIDENCE_PATH_UNSAFE`; ordinary denial=`EVIDENCE_CORRUPT`; drift=`GcStoreChangedError` | planning lock matrix | 1b+1h/A |
| S09/_apply_registered | O1–O3 acquire | prepared authority后的unsafe/missing/identity drift；ordinary denial | B15 | 是 | authority loss/drift=`GC_STORE_CHANGED`; ordinary denial且无drift=`GC_DELETE_FAILED`; 0 deletion | apply lock matrix | 1b+1k/A |
| S09/_apply_reconstructed | O1–O3 acquire | any unprepared store/lock unsafe或identity failure | r001 closure | 是 | `GC_PLAN_INVALID`; 0 deletion | reconstructed nodes | 1b+1k/A |
| S09 release | O8 | unlock-only/close-only/both，无 body primary | S6.1 | Windows | fixed `CORRUPT`, 两清理均尝试 | run11b节点 | 1b/A（重建时必须重放） |
| S09 release | O8 | body raises typed primary + cleanup failure | priority | Windows | primary保留 | plan/apply pre-delete | 1b/A（重建时必须重放） |
| S09 release | O8 | body正常返回且未提交 mutation + cleanup failure | priority | Windows | `CORRUPT`, fixed/path-free | direct lock节点待补 | 1b/B |
| S09/_apply_registered release | O8 | body正常返回且已提交 GC delete + cleanup failure | B15 truth | Windows | `success=false, code=GC_PARTIAL_DELETE`；保留exact deleted/retained paths与bytes；body已有exact partial则原样保留 | 无 | 1k/**B blocker** |
| S09/_consume_authorization release | commit/O8 | ledger publication + cleanup failure | single-use truth | Windows | confirmed commit=`GC_AUTHORIZATION_CONSUMED`、零删除、ledger保留不可重用；unconfirmed=`GC_AUTHORIZATION_INVALID`、零删除 | 无 | 1i/B |
| S09 POSIX release | O8 | flock/unlock/close | S6.1 | 当前不可原生 | 同一caller-specific contract，由POSIX owner提证据 | 无原生 | C |

## 6. Catalog / SQLite authoritative query 矩阵

| 格 | 阶段 | 状态 | 规范 | 可执行 | 预期 | 测试 | 类 |
|---|---|---|---|---:|---|---|---|
| C01/query grammar | O0 | invalid filter/limit/time | B15 | 是 | `INVALID` | request-before-db | 1e/A |
| C01 catalog lifecycle | O1 | 从未构建 | B15 | 是 | `INVALID` | unbuilt | 1e/A |
| C01+S01 root/main | O1–O3/O7 | root非目录、link/casefold/hardlink/swap | B15 | 是 | `PATH_UNSAFE` | file-root/swap | 1e/A |
| C04 main consumer | O1–O7 | malformed/unreadable/schema/query/fetch | B15/S6.1 | 是 | `CORRUPT` | malformed/drop/query | 1e/A |
| C07 row projection | post-O8 | fetched row字段/type/bound/canonical投影非法 | B15/S6.1 | 是 | `CORRUPT`，cleanup已完成，不存在cleanup交叉 | invalid-row nodes | 1e/A |
| C04 same inode | O1→O3/O7 | in-place合法 donor rewrite | B15 | 是 | `CORRUPT` | rewrite node | 1e/A |
| C03 offset-18 journal header | O4 | lseek/read/reset OSError | S6.1 | 是 | `CORRUPT` path-free | 无逐 syscall | 1e/B |
| C03 offset-18 journal header | O4–O5 | 不是exact 2-byte `01 01` | B15 | 是 | `CORRUPT` | 间接 | 1e/B |
| C04 connect | O4 | SQLite connect failure | S6.1 | 是 | `CORRUPT` | catch存在，无精确节点 | 1e/B |
| C04 database_list | O4 | malformed/error/main stat | B15 | 是 | shape/error/main stat denial=`CORRUPT`; main identity mismatch=`PATH_UNSAFE` | mismatch有，shape不足 | 1e/B |
| C04 journal_mode | O4/O7 | mode非 DELETE | single-file authority | 是 | `CORRUPT` | node | 1e/A |
| C02 `-wal/-shm/-journal` | O1/O7 | pre/post regular存在 | B15 | 是 | `CORRUPT` | wal/shm；缺journal与post逐项 | 1e/B |
| C02 auxiliary | O1/O7 | unsafe/link/permission | B15/S6.1 | 是 | unsafe=`PATH_UNSAFE`; permission=`CORRUPT` | wal link；缺shm/journal逐项 | 1e/B |
| C04 consumer binding | O4–O7 | regular未绑定aux/内容矛盾 | B15 | 是 | regular auxiliary或same-main内容矛盾=`CORRUPT`; link/reparse/casefold/path-handle identity mismatch=`PATH_UNSAFE` | WAL/SHM历史节点 | 1e/A，重建时保留 |
| S05/catalog.query final handle/path | O6–O7 | denial/missing/mismatch | B15/S6.1 | 是 | denial=`CORRUPT`; missing或identity mismatch=`PATH_UNSAFE` | path有，fstat denial不足 | 1e/B |
| C05 SQLite close | O8 | cleanup-only | S6.1 | 是 | `CORRUPT` fixed/path-free | run11b | 1e/A（重建时必须重放） |
| C06 descriptor close | O8 | cleanup-only | S6.1 | 是 | `CORRUPT` fixed/path-free | run11b | 1e/A（重建时必须重放） |
| C05+C06 primary×SQLite/descriptor/both cleanup | O8 | primary + cleanup failure | priority | 是 | typed primary保留；两个cleanup均尝试；无raw text；C07 row projection发生在cleanup后并单列 | 单项有，both不足 | 1e/B |
| C04 Windows pathname reader | O4 | validated main 与实际 reader | platform | Windows | 同 file ID | foreign swap | 1e/A |
| C04 POSIX fd reader | O4 | `/proc/self/fd`/`/dev/fd` | platform | 当前不可原生 | 同 inode，DELETE-only | 无原生 | C |
| C08/C09 rebuild manifest scan/read | O1/O7 + S06 | enumeration permission=`CORRUPT`; unsafe=`PATH_UNSAFE`; manifest read按S06 | B15/S6.1 | 是 | typed/path-free | 节点不完整 | 1f/B |
| C10 rebuild publication | publish | build/replace/fsync | B136 | 是 | raw publication seam | rebuild tests | E，不进typed catch |
| freshness marker | lifecycle | dirty/rebuild/query | spec 6.3 | 未实现 | T10.3 | 无 | D |

## 7. GC planning / snapshot 矩阵

| 格 | 状态 | 规范 | 可执行 | 预期 | 测试 | 类 |
|---|---|---|---:|---|---|---|
| lock/store identity | missing/swap | B15 | 是 | `GcStoreChangedError` | matrix | A |
| lock/store identity | permission，无 drift | S6.1 | 是 | `EVIDENCE_CORRUPT` | matrix | A |
| top dir | 初始一致缺失 | accepted planning | 是 | normal empty | control | A |
| G03/plan top-directory iterdir | permission，无 drift | S6.1/B15 | 是 | `EVIDENCE_CORRUPT`, fixed/path-free | matrix | 1h/A |
| G03/plan entry lstat | permission，无 drift | S6.1/B15 | 是 | 直接抛fixed/path-free `EVIDENCE_CORRUPT`；不写entry `read_error` | 当前实现一致；缺exact node | 1h/B |
| entry/top/dir | disappearance/identity drift | B15 | 是 | `GC_STORE_CHANGED` | snapshot nodes | A |
| object read | permission，planning conservative | accepted | 是 | corrupt entry + retention | node | A |
| G02 non-strict file identity cleanup-only | close/handle cleanup failure，无已确认drift | S6.1/B15 | Windows | 该entry写`read_error`，标corrupt并conservative retain；不向plan caller裸抛 | 精确cleanup节点缺 | 1h/B |
| G02 non-strict file identity drift + cleanup failure | 已确认identity drift | B15 priority | Windows | `GcStoreChangedError`优先 | drift+cleanup节点 | 1h/A |
| root/manifest | malformed/noncanonical | accepted | 是 | corrupt/unknown + retention | nodes | A |
| second snapshot | mismatch | B15 | 是 | `GC_STORE_CHANGED` | race node | A |
| named plan fault | raw OSError | B136 | 是 | raw crash seam | node | E |
| mutation lock cleanup | primary + cleanup | priority | Windows | typed primary保留；若body已commit progress则按1k exact partial裁定 | run11b仅precommit | 1h/A + 1k/B |
| POSIX planning lock | cleanup | platform | 非原生 | same contract | 无 | C |

## 8. GC authorization / ledger 矩阵

| 格 | 状态 | 规范 | 可执行 | 预期 | 测试 | 类 |
|---|---|---|---:|---|---|---|
| input | non-GcPlan | B15 | 是 | `EVIDENCE_INVALID` | node | A |
| reconstructed/unregistered | invalid plan | r001 closure | 是 | `GC_PLAN_INVALID`, 0 delete | nodes | A |
| token | already consumed | auth | 是 | `GC_AUTHORIZATION_CONSUMED` | competition | A |
| token/digest | wrong | auth | 是 | `GC_AUTHORIZATION_INVALID` / `GC_PLAN_DIGEST_MISMATCH` | nodes | A |
| G01 stable parent | disappearance/identity drift，含open/close交叉 | B15 | Windows | `GC_STORE_CHANGED`，primary保留 | nodes | 1i/A |
| G01 stable parent | permission或cleanup-only，无drift | accepted map | Windows | `GC_AUTHORIZATION_INVALID`，零删除，fixed/path-free | ordinary node；cleanup-only缺 | 1i/B |
| POSIX parent guard | platform | C | simulated | fail closed；需原生 owner | 模拟 | C |
| ledger CREATE_NEW | confirmed commit + cleanup fail | single-use truth | Windows | `GC_AUTHORIZATION_CONSUMED`、零删除、ledger保留且不可重用 | 无 | 1i/**B** |
| ledger CREATE_NEW | unconfirmed commit/storage fail | fail-closed auth | Windows | `GC_AUTHORIZATION_INVALID`、零删除；不得声称consumed | 无 | 1i/**B** |
| pre-lock store | mismatch | B15 | 是 | `GC_STORE_CHANGED` | node | A |
| pre-lock store | permission，无 mismatch | B15 | 是 | `GC_DELETE_FAILED` | node | A |

## 9. GC apply / delete / final snapshot 矩阵

| 阶段 | 状态 | 规范 | 可执行 | 预期 | 测试 | 类 |
|---|---|---|---:|---|---|---|
| initial strict snapshot | permission，无 drift | B15 | 是 | `DELETE_FAILED`, 0 progress | matrix | A |
| G02 strict file identity cleanup-only | permission/close failure，无drift，0/prior commit | S6.1/B15 | Windows | `GC_DELETE_FAILED` / `GC_PARTIAL_DELETE` exact progress | 精确cleanup节点缺 | 1k/B |
| G02 strict file identity drift + cleanup failure | 已确认drift，0/prior commit | B15 priority | Windows | `GC_STORE_CHANGED` / `GC_PARTIAL_DELETE` exact progress | drift+cleanup节点 | 1k/A |
| initial strict snapshot | confirmed drift | B15 | 是 | `STORE_CHANGED` | matrix | A |
| per-target snapshot | permission, 0 commit | B15 | 是 | `DELETE_FAILED` | matrix | A |
| per-target snapshot | permission, prior commit | B15 | 是 | `PARTIAL`, exact progress | matrix | A |
| per-target snapshot | drift, 0/prior commit | B15 | 是 | `STORE_CHANGED` / `PARTIAL` | matrix | A |
| final snapshot | permission, 0/prior commit | B15 | 是 | `DELETE_FAILED` / `PARTIAL` | matrix | A |
| final snapshot | drift, 0/prior commit | B15 | 是 | `STORE_CHANGED` / `PARTIAL` | matrix | A |
| delete handle | missing/identity/link/type/size mismatch | B15 | Windows | `STORE_CHANGED` / `PARTIAL` | nodes | A |
| handle read 1/2 | exact EOF/digest mismatch | B15 | Windows | `STORE_CHANGED` / `PARTIAL` | digest nodes；ReadFile短读不足 | B |
| excluding-target snapshot | other state drift | B15 | Windows | `STORE_CHANGED` / `PARTIAL` | concurrent nodes | A |
| SetDisposition | failure before commit | B15 | Windows | `DELETE_FAILED` / prior `PARTIAL` | nodes | A |
| committed disposition | close failure | truth | Windows | `PARTIAL`, exact progress | node | A |
| committed disposition | directory flush logical seam | truth | monkeypatch可执行；Windows native `_flush_directory` no-op | `PARTIAL`, exact progress；不得新增Win32 durability架构 | 逻辑节点待补；native N/A | 1j/B；native E |
| after-delete fault | after commit | B136 | 是 | `PARTIAL`, exact progress | node | A |
| body normal return with committed delete | mutation-lock cleanup fail | truth/priority | Windows | `success=false, GC_PARTIAL_DELETE`，保留exact deleted/retained/bytes；body已有partial原样保留 | 无 | 1k/**B blocker** |
| POSIX delete | unsupported/fail closed | platform | 模拟 | `DELETE_FAILED`, target retained | 模拟 | C |

## 10. primary error × cleanup error 总矩阵

| owner | primary success | typed primary | committed side effect | cleanup-only预期 | primary+cleanup预期 | 覆盖 |
|---|---|---|---|---|---|---|
| S06 managed stable bytes | bytes | CORRUPT/PATH_UNSAFE | 无 | `CORRUPT` | primary保留；确认drift则PATH_UNSAFE优先 | 1c/B cleanup |
| S07 source hash | digest | INVALID/PATH_UNSAFE | 无 | `INVALID` | primary保留；确认drift则PATH_UNSAFE优先 | 1d/B cleanup |
| S07 managed hash | digest | CORRUPT/PATH_UNSAFE | 无 | `CORRUPT` | primary保留；确认drift则PATH_UNSAFE优先 | 1c/B cleanup |
| S08 source copy | ref-before-publication | INVALID/PATH_UNSAFE | temp-only未发布 | `INVALID` | primary保留；确认drift则PATH_UNSAFE优先 | 1d/B cleanup |
| S09 non-ledger/non-GC lock | body return | typed Evidence | 无 | `CORRUPT` | typed primary保留 | 1b/B direct |
| S09 ledger lock | auth commit result | auth typed/result | token可能commit | 未commit=`GC_AUTHORIZATION_INVALID`; committed=`GC_AUTHORIZATION_CONSUMED` | commit truth优先 | 1i/B |
| S09 outer apply lock | GcResult | typed/result | delete可能commit | 无commit=`CORRUPT`由1k映`DELETE_FAILED`; commit=`PARTIAL` exact | body partial原样；不得重建零进度 | 1k/B blocker |
| C05+C06 query cleanup | rows | CORRUPT/PATH_UNSAFE | 无 | `CORRUPT` | primary保留，SQLite+fd均尝试；C07 projection在cleanup后 | 1e/B both |
| G01 authorization parent | identity | GcStoreChanged | 无 | `GC_AUTHORIZATION_INVALID` | drift primary→`GC_STORE_CHANGED` | 1i/B cleanup-only |
| G02 planning non-strict identity | entry metadata | GcStoreChanged | 无 | entry read_error+retain | drift primary保留 | 1h/B cleanup-only |
| G02 apply strict identity | identity | GcStoreChanged/result | prior delete可能commit | 0 commit=`GC_DELETE_FAILED`; prior commit=`PARTIAL` exact | drift: 0=`STORE_CHANGED`, prior=`PARTIAL` | 1k/B cleanup-only |
| G08 identity-bound delete | outcome | drift/result | current/prior delete可能commit | 0 commit ordinary=`DELETE_FAILED`, drift=`STORE_CHANGED`; any commit=`PARTIAL` exact | committed close/flush不得覆盖progress | 1j/B flush |
| publication/fault seams | published/not | raw fault contract | 可能commit | 保留原 lifecycle | 不在taxonomy catch内 | E |

## 11. Windows / POSIX Evidence owner

| 项目 | Windows owner | POSIX owner | 当前处置 |
|---|---|---|---|
| reparse/junction/Win32 file ID | 本项目 Windows 门禁 | N/A | A |
| msvcrt lock/unlock/handle cleanup | 本项目 Windows 门禁 | N/A | A/B |
| Win32 identity-bound delete | 本项目 Windows 门禁 | N/A | A/B |
| POSIX flock/open/fstat/unlink/close | N/A | 后续 Linux owner | C，不由 Windows 代签 |
| `/proc/self/fd`/`/dev/fd` SQLite binding | N/A | 后续 Linux owner | C |
| 跨平台纯模型/错误投影 | 双 Python Windows可执行 | 后续平台回归 | A |

### POSIX C格的精确 owner 与门禁

- Owner：`local Codex POSIX acceptance reviewer`，只读验收该单元候选 SHA。
- 执行时点：每单元 Windows 完整 diff CLEAN 后可记 `DEFERRED(POSIX)`；Task 10 累计 acceptance 前必须转为 PASS。
- 为避免未来 node 名变化造成选择遗漏，1b–1d保守运行完整Store文件，1e–1f完整Catalog文件，1g–1k完整GC文件；1a运行四文件。
- reviewer 使用下面唯一脚本，传入两个普通 argv：单元ID和review package中记录的40字符candidate SHA。脚本没有 selector/path占位；路径、venv、JUnit均由这两个值确定。

```sh
set -eu
unit="$1"
expected_sha="$2"
case "$unit" in
  1a) selectors="tests/test_evidence_model.py tests/test_evidence_store.py tests/test_evidence_catalog.py tests/test_evidence_gc.py" ;;
  1b|1c|1d) selectors="tests/test_evidence_store.py" ;;
  1e|1f) selectors="tests/test_evidence_catalog.py" ;;
  1g|1h|1i|1j|1k) selectors="tests/test_evidence_gc.py" ;;
  *) echo "unknown unit" >&2; exit 2 ;;
esac
case "$expected_sha" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) echo "candidate must be a full lowercase SHA" >&2; exit 2 ;;
esac
repo="$(git rev-parse --show-toplevel)"
test -z "$(git -C "$repo" status --porcelain)"
test "$(git -C "$repo" rev-parse "$expected_sha^{commit}")" = "$expected_sha"
root="/tmp/stm32tk-t10-${unit}-${expected_sha}"
test ! -e "$root"
git -C "$repo" worktree add --detach "$root" "$expected_sha"
test -z "$(git -C "$root" status --porcelain)"
for version in 3.12 3.10; do
  venv="/tmp/stm32tk-t10-venv-${unit}-${expected_sha}-${version}"
  test ! -e "$venv"
  "python${version}" -m venv --system-site-packages "$venv"
  "$venv/bin/python" -m pip install --no-index --no-deps --no-build-isolation -e "$root/tools/stm32-toolkit"
  "$venv/bin/python" -I -c "from pathlib import Path; import stm32_toolkit; expected=Path(r'$root/tools/stm32-toolkit/src/stm32_toolkit').resolve(); actual=Path(stm32_toolkit.__file__).resolve().parent; assert actual == expected, (actual, expected)"
  evidence="/tmp/stm32tk-t10-${unit}-${expected_sha}-${version}"
  test ! -e "$evidence"
  mkdir "$evidence"
  (cd "$root/tools/stm32-toolkit" && "$venv/bin/python" -m pytest -p no:cacheprovider $selectors --basetemp "$evidence/pytest" --junitxml "$evidence/pytest.xml")
  "$venv/bin/python" -c "import xml.etree.ElementTree as E; r=E.parse(r'$evidence/pytest.xml').getroot(); s=r if r.tag=='testsuite' else next(iter(r)); assert int(s.attrib.get('failures','0'))==0 and int(s.attrib.get('errors','0'))==0; print(s.attrib)"
done
test -z "$(git -C "$root" status --porcelain)"
if pgrep -af "stm32tk-t10-(venv-)?${unit}-${expected_sha}.*(python|pytest)"; then exit 1; fi
```

每份报告必须记录完整argv、两个JUnit hash、所有skip node/reason、import resolved path、工作树SHA/status和进程审计。POSIX destructive delete维持现有unsupported/fail-closed合同，不新增unlink engine；Windows结果不得代签。

## 12. 已冻结的七项裁定

1. S06 cleanup-only=`EVIDENCE_CORRUPT`；S07 source=`INVALID`、managed=`CORRUPT`；S08=`INVALID`。typed primary优先；cleanup重观察确认path/link/identity drift时=`PATH_UNSAFE`。
2. caller source same-inode bytes/size/mtime mutation=`PATH_UNSAFE`；managed object/manifest/catalog同一identity内容矛盾=`CORRUPT`；pathname/handle identity、link/reparse/casefold变化=`PATH_UNSAFE`。
3. GC删除已commit后outer lock cleanup失败=`success=false, GC_PARTIAL_DELETE`，保留exact deleted/retained/bytes；body已有exact partial则原样保留。
4. ledger CREATE_NEW已commit后cleanup失败=`GC_AUTHORIZATION_CONSUMED`、零删除、ledger保留不可重用；未确认commit=`GC_AUTHORIZATION_INVALID`、零删除、不得声称consumed。
5. Catalog 1e必须逐项覆盖C03 seek/read/reset、C04 connect/database_list/main-stat/journal/query/fetch、三个sidecar pre/post、S05 final fstat/path与no-primary/typed-primary×C05 SQLite-close/C06 descriptor-close/both；C07 row projection在cleanup后单列。
6. Win32 ReadFile非零短chunk是成功控制；只对API failure、expected-size前premature zero、最终size/digest mismatch失败，并按prior commit=`STORE_CHANGED/PARTIAL`。Windows `_flush_directory` native no-op标N/A/E；仅monkeypatch逻辑seam要求`PARTIAL` exact progress。
7. POSIX按上节由指定owner双Python原生执行；可暂记DEFERRED，但Task 10累计验收前必须PASS。

## 13. 无环执行单元与 Git 持久化

| 单元 | 单一交付面 | exact product paths | exact test paths |
|---|---|---|---|
| 1a | typed-error ABI机械原子迁移 | `tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py`; `tools/stm32-toolkit/src/stm32_toolkit/evidence/model.py`; `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py`; `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py`; `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_model.py`; `tools/stm32-toolkit/tests/test_evidence_store.py`; `tools/stm32-toolkit/tests/test_evidence_catalog.py`; `tools/stm32-toolkit/tests/test_evidence_gc.py`；禁止I/O状态流变化 |
| 1b | Store mutation-lock | `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py` | `tools/stm32-toolkit/tests/test_evidence_store.py` |
| 1c | Store managed stable-read/hash | `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py` | `tools/stm32-toolkit/tests/test_evidence_store.py` |
| 1d | Store caller-source ingest | `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py` | `tools/stm32-toolkit/tests/test_evidence_store.py` |
| 1e | Catalog SQLite query authority | `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py` | `tools/stm32-toolkit/tests/test_evidence_catalog.py` |
| 1f | Catalog rebuild manifest scan/read taxonomy | `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py` | `tools/stm32-toolkit/tests/test_evidence_catalog.py` |
| 1g | `put_root` existing-read/lost-create | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` |
| 1h | GC planning/snapshot | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` |
| 1i | GC authorization/ledger | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` |
| 1j | GC identity-bound delete primitive | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` |
| 1k | GC apply/progress/outer cleanup | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` |

依赖严格为1a→1b→1c→1d→1e→1f→1g→1h→1i→1j→1k；测试可读取上游公共行为，但不得修改第二产品域。若1k发现必须改变Store lock API，停止并先创建新的docs-only前置单元，禁止回边混改。

矩阵 CLEAN 前禁止产品修改。矩阵 CLEAN 后第一步不是实现，而是创建 docs-only Git 提交：修订tracked Task 10 spec §8/§9并保存本矩阵、十一单元allowed paths/依赖/门禁。该提交成为新implementation base；冻结候选`ee2b153`不得作为父提交或整包cherry-pick来源。之后每单元只选择其A/B格，D/E不得混入。
