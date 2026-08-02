# 项目进度

> 每次阶段验收后更新：已完成项、命令、结果、遗留问题。

## 当前状态

**工程闭环 0.2.1-p0-fixes（合成数据）** — 修复跨 split 泄漏门禁、Receiver 幂等/安全通知、锁屏隐私、评测默认 TFLite、剪枝预算回退、量化 hybrid 标注。  
**语种目标调整（2026-07）：当前验收仅中文（zh）；英/印地/印尼暂缓。**  
**历史训练产物归档（2026-07-28）：** `recent/prior_training/`（含 interim 标注、processed 切分、Colab 导出、旧 artifacts/reports、release-0.2.0 包）；活动目录已清空占位，重训/重标写回原路径。  
**未宣称**事务召回 ≥98%（冻结真标中文测试集与 4GB/6GB 真机 PSS 仍缺）。

### Recall v3 准备（2026-08-01）

- [x] 切分改为 template/sender/parent/fingerprint 连通分量；任一关系相连即同 split。
- [x] 从两个已审计原始源重建训练冻结集：train 11221 / validation 1402 / test 1402，泄漏门禁 PASS。
- [x] 预留事务专项集 600 条，OTP/银行/物流/订单/还款/运营商各 100；关联组件共排除 1185 条，防止进入训练。
- [ ] 事务专项集仍需两名真实人工独立填写 A/B 表。现有 `deepseek_*`、`llm_*`、`audit_*` 是自动化流程标识，不能作为双人金标。
- [x] Teacher/Student 增加事务 CE 权重、统一归一化、best-checkpoint 与非事务类别保护门禁。
- [x] Student validation 硬门禁：事务 Recall ≥0.985、事务 Precision ≥0.92、Macro-F1 ≥0.86、HARASS F1 ≥0.80、FRAUD Recall ≥0.80；量化后再次要求事务 Recall ≥0.985，未通过时不读取锁定 test。
- [x] formal v2 Full-INT8（92048 B）已导出 Android；SHA `b4e57ad3a48fc5765fa022b725e801a9f0bd8f8121d6e7ef1b67b26cf31fc6b3` 与 metadata 一致。
- [ ] 在批准的本地/内网 GPU 执行 `training/scripts/run_recall_v3.py`；不得上传短信数据到公共 Colab。

### Recall v4 事务保护（2026-08-01）

- [x] 本地 RTX 4070 复现实验：Teacher validation Macro-F1 0.829、事务 Recall 0.947；默认蒸馏学生 Macro-F1 0.818、事务 Recall 0.916，证明单纯类别权重不能达到 0.985。
- [x] 修复 checkpoint 选择：没有 checkpoint 全部过门禁时，按“最差门禁缺口”选择，不再只追逐事务 Recall。
- [x] Student 改为共享 ByteCNN 骨干的 5-logit 单输出：前四维保持固定类别顺序，第五维为 `TRANSACTION vs REST` 保护头；增加约 100 个参数。
- [x] 新增银行、物流、订单、还款、运营商高精度事务保护规则；与欺诈规则冲突时进入 REVIEW，不自动放行。
- [x] Python/Android 路由均支持保护头和事务规则；对旧四输出模型保持 metadata 向后兼容。
- [x] `evaluate.py --mode pipeline` 与 `evaluate_pipeline_stages.py` 分开报告模型和完整保护 Pipeline 指标；默认只读 validation。
- [x] 锁定 test 仍由完整 validation Pipeline 门禁保护；门禁未通过时不量化、不读取 test、不覆盖 Android 模型。
- [x] Python 轻量测试：42 passed。
- [ ] 执行 `training/scripts/run_recall_v4.py --skip-teacher` 重新训练双头学生并评估 validation Pipeline；需要 GPU 实验。
- [ ] Android JVM 测试需先配置 JDK 17 / `JAVA_HOME`。

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

## 你需要亲自完成的事项（详细步骤）

完整 Colab 手册见：[colab-training-guide.md](./colab-training-guide.md)

摘要：

1. **本机**跑 `generate_synthetic_dataset` → `build_dataset` → `check_split_leakage`（必须 PASS）
2. **Colab GPU** 下载 `google-bert/bert-base-multilingual-cased`【第三方】到本地目录
3. Colab 执行 `train_teacher.py --model-path ...` → 产出 `teacher_logits_manifest.json`
4. 再跑 `distill_student.py`（不要 `--hard-only`）→ `prune` → `quantize` → `verify` → `evaluate --mode tflite`
5. 把 `artifacts/` + metrics + manifests 下载回本机，执行 `export_android_assets.py` 后编 APK
6. **禁止**把真实短信上传 Colab；合成指标不得宣称事务召回 ≥98%

## 遗留问题

1. 真实/合规标注**中文**冻结测试集（每类 ≥500）与双人标注（内网，勿上公共 Colab）；英/印地/印尼不纳入本期冻结硬门槛
2. 教师 BERT 在 Colab/训练机微调 + 真蒸馏（见 colab 手册）
3. 4GB/6GB 真机 PSS / 时延 / 默认短信飞行模式验收
4. 事务召回 ≥98% 达标前不得在审核报告写 PASS
5. MMS 仍为占位；发送未写 Sent Provider
6. Android 仪器化测试矩阵（multipart/幂等/隐私）仍缺
7. 旧 INT8 模型可能仍为 hybrid — 需在无泄漏数据上重跑全训练链
