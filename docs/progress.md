# 项目进度

> 每次阶段验收后更新：已完成项、命令、结果、遗留问题。

## 当前状态

**工程闭环 0.2.1-p0-fixes（合成数据）** — 修复跨 split 泄漏门禁、Receiver 幂等/安全通知、锁屏隐私、评测默认 TFLite、剪枝预算回退、量化 hybrid 标注。  
**未宣称**事务召回 ≥98%（冻结真标测试集与 4GB/6GB 真机 PSS 仍缺）。

异机构建提示：仓库路径含中文时，建议使用 ASCII junction：`C:\dev\Android_SMS_Classifier`。

## 已完成

### 阶段 0/1

- [x] 目录树 / Makefile / README / LICENSE
- [x] `android.overridePathCheck=true`（非 ASCII 路径）
- [x] Manifest 无 `INTERNET`
- [x] HARASS 规则资产 `harass_rules.json`

### P0 修复（2026-07-16）

- [x] 废弃泄漏切分脚本 `_generate_synthetic_data.py`（拒绝执行）
- [x] `generate_synthetic_dataset.py` 只写 raw；`build_dataset.py` 统一 group 切分 + 泄漏门禁
- [x] `check_split_leakage.py` + `training/src/leakage.py`；当前合成集 **leakage PASS**（train 157 / val 13 / test 14）
- [x] Receiver：幂等 `deliverKey`、超时 category=`UNKNOWN`、异常仍安全通知
- [x] 通知锁屏隐私：`VISIBILITY_PRIVATE` + public redacted（无正文/OTP）
- [x] Inbox 隔离 SUSPECT/REVIEW
- [x] `evaluate.py` 默认 TFLite；`--mode rule` 必须显式；塌缩单类退出码 3
- [x] 蒸馏类别权重 + 验证塌缩门禁；剪枝 25→15→10 预算回退；量化记录 hybrid vs full INT8

### LiteRT / SDK

- [x] `LiteRtClassifier` 反射加载；INT8 输出反量化尝试
- [x] 无模型时规则降级 + REVIEW（不再默认 TRANSACTION）

### App 闭环代码

- [x] SmsDeliver：先写 Provider → 500ms 超时 REVIEW；不自动删除
- [x] 可疑/复核可恢复收件箱
- [x] 评测页摘要 + 脱敏导出；性能页本地测速

## 命令记录

| 日期 | 命令 | 结果 |
|------|------|------|
| 2026-07-16 | junction + `gradlew :classifier-sdk:test :app:assembleDebug` | 先前 36/18 tests；需在 junction 复跑 |
| 2026-07-16 | `generate_synthetic_dataset` + `build_dataset --augment-train` + `check_split_leakage` | leakage PASS；manifest SHA 已刷新 |
| 2026-07-16 | `pytest training/tests` | **18 passed** |

## 遗留问题

1. 真实/合规标注冻结测试集（每类 ≥500）与双人标注
2. 教师 `bert-base-multilingual-cased` 本地缓存后跑 `train_teacher.py` 再蒸馏
3. 4GB/6GB 真机 PSS / 时延 / 默认短信飞行模式验收
4. 事务召回 ≥98% 达标前不得在审核报告写 PASS
5. MMS 仍为占位；发送未写 Sent Provider；SAF 评测导入未完成
6. Android 仪器化测试矩阵（multipart/幂等/隐私）仍缺
7. 旧 INT8 模型可能仍为 hybrid 且在塌缩数据上训练 — 需在无泄漏数据上重跑 distill→prune→quantize
