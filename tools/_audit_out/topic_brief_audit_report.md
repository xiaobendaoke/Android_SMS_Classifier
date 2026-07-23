# 课题指标对照审核报告

**日期:** 2026-07-23  
**环境:** Pixel_9a 模拟器 + Debug APK（`app-debug.apk`，约 32 MB）  
**结论总览:** 工程交付物与离线合规 **可审且基本通过**；课题硬指标（事务召回 ≥98%、≤100MB PSS、正式 ≤500ms）**证据不足 / 未达标宣称**；冒烟评测暴露分类质量问题。

---

## 1. 执行证据摘要

### 1.1 启动与权限
- 冷启动 `com.oppo.smsclassifier/.MainActivity` 成功（PID 存活）
- `adb pm grant` 授予 `READ_SMS` / `RECEIVE_SMS` / `POST_NOTIFICATIONS` 后无 `FATAL EXCEPTION` / `SecurityException` 闪退
- 收件箱展示「暂无短信」（模拟器无入库短信属预期）

### 1.2 App 内离线评估（`sample_eval.json`，6 条）
脱敏导出：`tools/_audit_out/eval_redacted.json`

| id | 期望 | 预测 | action | conf | ms | reasonCode | 对错 |
|----|------|------|--------|------|-----|------------|------|
| 1 | TRANSACTION (zh 银行) | TRANSACTION | INBOX | 99.9% | 4.5 | MODEL_PREDICTION | ✓ |
| 2 | TRANSACTION (en OTP) | AD | REVIEW | 57.1% | 1.7 | MODEL_LOW_CONFIDENCE | ✗ |
| 3 | AD (zh 营销) | AD | SUSPECT | 84.9% | 2.0 | AD_HINT | ✓ |
| 4 | FRAUD (zh 中奖) | AD | REVIEW | 41.8% | 1.5 | MODEL_LOW_CONFIDENCE | ✗ |
| 5 | FRAUD (hi) | **TRANSACTION** | **INBOX** | 80.5% | 1.8 | MODEL_PREDICTION | ✗ 高危误放 |
| 6 | TRANSACTION (zh 12306) | TRANSACTION | INBOX | 79.5% | 1.6 | MODEL_PREDICTION | ✓ |

- **准确率: 50%（3/6）**
- **缺口:** 无 HARASS 样本；无印尼语 (id) 样本；`expectedAction` 未计入评分

### 1.3 性能页（模拟器冒烟，非正式验收）
- P50 **1.0 ms** / P95 **2.0 ms** / P99 **2.0 ms**
- 吞吐量 **780.8 msg/s**
- 模型路径：**已加载 TFLite**
- UI 明确提示：额外内存 ≤100 MB 需真机 PSS

### 1.4 可疑 / 待复核 / 可解释性
- 「可疑」「待复核」页可进入（当前空列表文案正常）
- 代码确认恢复入口：`SuspectScreen` / `ReviewScreen` → `action=INBOX`
- 详情页字段：category / action / confidence / **reasonCode** / **ruleIds** / modelVersion / rulesVersion  
  （[`MessageDetailScreen.kt`](android/app/src/main/java/com/oppo/smsclassifier/ui/detail/MessageDetailScreen.kt)）
- Receiver：先写 Provider，**500ms** 超时 → `REVIEW`，不自动删除（[`SmsDeliverReceiver.kt`](android/app/src/main/java/com/oppo/smsclassifier/receiver/SmsDeliverReceiver.kt)）
- 真实收信闭环（ROLE_SMS）本次模拟器未完整验证

### 1.5 合规与自动化
| 检查 | 结果 |
|------|------|
| `tools/check_no_network_permission.py` | **PASS**（10 个 Manifest 无 INTERNET） |
| `:classifier-sdk:test` | **17/18 PASS，1 FAIL** |
| 失败用例 | `classify_noModelUnknownText_reviewWithoutFakeTransaction`：expected `REVIEW` but was `SUSPECT`（`"hello there"`） |
| Debug APK | 存在 |
| classifier-sdk-release.aar | 存在（约 132 KB，2026-07-16） |

### 1.6 文档交付清单
均 **PRESENT**: `architecture.md`, `sdk-api.md`, `model-card.md`, `privacy-threat-model.md`, `android-integration.md`, `colab-training-guide.md`, `performance-report.md`, `release-audit-report.md`, `multilingual-report.md`, `open-source-notices.md`

### 1.7 硬指标（仓库已有评测，非本次模拟器宣称）
来源：[`training/reports/metrics/evaluate.json`](training/reports/metrics/evaluate.json)

| 指标 | 数值 | 宣称 |
|------|------|------|
| transaction_recall | **0.898**（约 89.8%） | `claim_allowed: false` |
| transaction_recall_ci95 | [0.850, 0.931] | 上限仍 < 98% |
| accuracy / macro_f1 | 0.868 / 0.813 | 合成/小冻结集 |
| PSS ≤100 MB | 未测 | [`docs/performance-report.md`](docs/performance-report.md) 真机表为空 |
| 正式延迟 4GB/6GB | 未测 | 同上 |

---

## 2. 课题条款对照表

| 课题要求 | 判定 | 证据 | 缺口 / 下一步 |
|---------|------|------|----------------|
| 全链路：SMS 读取 → NLP → 规则 → 可视化+依据 | **部分 Pass** | Demo 离线评估可跑；导出含 reasonCode；详情页有规则/原因字段；可疑/复核页存在 | 模拟器无入库短信，未演示详情页实数据；ROLE_SMS 收信闭环未完整审 |
| 中文细分类 事务/广告/骚扰/诈骗 | **证据不足** | zh 冒烟 3 对 1 错（#4 诈骗→广告）；训练评估含四类 | App 冒烟集 **无 HARASS**；#4 诈骗漏检 |
| 扩展 en / hi / id | **Fail（冒烟）** | en OTP→AD；hi 诈骗→TRANSACTION/INBOX；perf 探针含印尼文但 sample_eval **无 id** | 补 OTP/多语规则与金标；扩展 sample_eval |
| 内存 ≤100MB | **证据不足** | 仅有预算文案与工程报告 Pending | 4GB/6GB 真机 PSS |
| 时延 ≤500ms | **冒烟 Pass / 正式证据不足** | 模拟器 P99=2ms；代码 500ms→REVIEW | 真机 ≥500 样本冷/热统计 |
| 事务召回 ≥98%（防误杀硬约束） | **Fail（相对硬门槛）** | evaluate.json recall≈89.8%，`claim_allowed=false`；冒烟 en OTP 误分 | 冻结双人金标 + 重训/规则加固后再评 |
| 零上云 / 短信不出设备 | **Pass** | 无 INTERNET 脚本 PASS；离线 TFLite | — |
| 可运行 Android Demo/SDK | **Pass** | APK 安装运行；AAR 存在；评估/性能页可用 | 修复 SDK 单测 1 失败 |
| 核心说明文档 | **Pass** | 上表 10 份关键文档齐全 | 可再补「课题对照」对外摘要 |

---

## 3. 审核结论（对课题「能否审完整」的落地回答）

1. **工程/交付维度：可审完整** — Demo 可跑、离线、无网络、文档与 SDK 产物齐；本次给出 Pass。  
2. **硬指标维度：不能审成 PASS** — ≥98% 召回与 ≤100MB 在现有证据下 **未达到 / 未测量**。  
3. **质量风险（应优先修）:**  
   - 英文验证码被判 AD（防误杀相关）  
   - 印地语诈骗被判 TRANSACTION+INBOX（高危）  
   - SDK 无模型降级路径单测失败（`SUSPECT` vs 期望 `REVIEW`）

**最终课题业务验收建议:** 维持 `PASS_ENGINEERING` / **不放行业务 PASS**，与 [`docs/release-audit-report.md`](docs/release-audit-report.md) 一致。
