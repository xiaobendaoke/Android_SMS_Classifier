# Android 端侧离线短信分类系统

> 面向 4GB/6GB 中低端 Android 设备的端侧离线短信四分类系统：零上云、无重型大模型、短信不出设备，实现「事务 / 广告 / 骚扰 / 诈骗」细分类与可解释输出。

## 项目简介

营销广告、骚扰推广与验证码、物流、银行动账等短信高度混杂，云端分类存在短信正文上传的隐私风险，重型大模型又难以部署到中低端设备。本项目提供一套端到端本地方案：

- **全链路本地处理**：短信读取 → 归一化 → 规则引擎 → Byte TextCNN → 决策路由 → 结果展示。
- **轻量模型**：Full-INT8 TFLite，模型仅约 101 KB，适配中低端设备。
- **防误杀设计**：规则优先保护事务短信，低置信与超时一律进入 REVIEW 兜底，永不自动删除短信。
- **高隐私**：App/SDK 无 `INTERNET` 权限，短信正文只在本机内存处理。
- **可解释输出**：返回类别、动作、置信度、耗时、原因码与命中规则，便于人工复核。

## 系统架构

```text
短信 Provider / Receiver
  → TextNormalizer（NFKC 归一化 / 混淆字符替换）
  → RuleEngine（事务保护 / 欺诈拦截 / 骚扰识别规则）
  → ByteEncoder（UTF-8 字节编码，固定长度 512）
  → LiteRtClassifier（TFLite INT8 推理）
  → DecisionRouter（INBOX / SUSPECT / REVIEW + 可解释依据）
```

关键设计：分类与处置分离，规则只影响动作、不篡改模型分类；模型负责细分类，规则与低置信兜底共同保证事务短信不被误杀。

## 当前指标

### 分类质量（中文 validation，Keras 独立评测）

| 门禁 | 目标 | 当前 | 状态 |
|------|------|------|------|
| TRANSACTION Recall | ≥0.985 | 0.9568 | 未达 |
| TRANSACTION Precision | ≥0.920 | 0.9258 | 达标 |
| Macro-F1 | ≥0.860 | 0.8864 | 达标 |
| HARASS F1 | ≥0.800 | 0.8194 | 达标 |
| FRAUD Recall | ≥0.800 | 0.8780 | 达标 |

> 说明：当前交付版本的事务类短信召回率未达到 98% 硬指标，其余四项门禁通过；完整口径见 `00_验收报告/最终验收报告.md`。

### 性能（模拟器工程测量）

| 配置 | p99 时延 | 吞吐 | PSS 暖启动 → 跑后 |
|------|---------|------|-------------------|
| 模拟器 4GB（Pixel_9a） | 3.6 ms | 395.7 msg/s | 37.9 MB → 59.5 MB |
| 模拟器 6GB（Pixel_9a_6G） | 93.4 ms | 64.9 msg/s | 38.3 MB → 44.2 MB |

> 说明：以上为 x86_64 模拟器工程测量（数据见 `05_指标报告/`），不代表真机结果。

### 模型

- 架构：Byte TextCNN（字节级编码，输入长度 512）。
- 量化：Full-INT8 TFLite，`101,696` B。
- SHA256：`b4c53f180ed3d23b0b01205f75610e174fe06fe5b9116e53d936a714f052baed`。
- Keras/TFLite 一致性：0.9964（≥0.99）。

## 目录结构

| 目录 | 说明 |
|------|------|
| `00_验收报告/` | 最终验收报告 |
| `01_模型/` | INT8 TFLite、FP32 Keras、量化报告、模型元数据 |
| `02_Android/` | Demo APK、SDK AAR、Android 三模块源码 |
| `03_规则引擎/` | 事务/广告/骚扰/诈骗/OTP 规则与归一化表 |
| `04_训练与数据/` | 训练源码、配置、数据快照与说明（仅内部使用） |
| `05_指标报告/` | 分类指标、模拟器性能、App 端批量评估 |
| `06_审计与合规/` | 发布审计、SBOM、权限清单、产物哈希 |

## 快速开始

### 安装 Demo

1. 将 `02_Android/app-debug.apk` 安装到 Android 8.0+（minSdk 26）设备或模拟器。
2. 首次启动授予短信读取/接收权限。
3. 使用三个页面：离线测评（内置样例或导入 JSON/JSONL）、短信判断（手动输入正文）、关于。

### 集成 SDK

SDK AAR：`02_Android/classifier-sdk-release.aar`。核心接口为 `SmsClassifier.classify(SmsInput)`，返回 `ClassificationResult`（类别、动作、置信度、原因码、命中规则等）。

```kotlin
val classifier: SmsClassifier = DefaultSmsClassifier(readAsset = ::readAsset, modelBytes = modelBytes)
val result = classifier.classify(
    SmsInput(
        sender = "10086",
        body = "【银行】您尾号1234的账户到账人民币500.00元",
        timestampMillis = System.currentTimeMillis()
    )
)
println(result.category)   // TRANSACTION / AD / HARASS / FRAUD
println(result.action)     // INBOX / SUSPECT / REVIEW
println(result.reasonCode) // 可解释依据
```

### 源码构建

```bash
cd 02_Android/android-src
./gradlew test
./gradlew :app:assembleDebug
```

构建前提：JDK 17+、Android SDK（compileSdk 34 / minSdk 26）；`local.properties` 中配置 `sdk.dir` 或设置 `ANDROID_HOME`。详细说明见 `02_Android/android-src/README-GRADLE.md`。

### 训练源码与数据

`04_训练与数据/` 包含训练核心模块（`src/`）、配置（`configs/`）与数据快照（`data/`）。本交付包聚焦最终产物，训练脚本与中间过程不随包提供；数据口径见 `04_训练与数据/data/README-数据.md`。

## 数据与合规

- 数据快照：train 11,095 / validation 1,398 / test 1,397 行，见 `04_训练与数据/data/README-数据.md`。
- 原始短信 JSONL 仅限内部审核与答辩使用，禁止公开、上传或二次分发。
- App/SDK 无 `INTERNET` 权限，运行链路零上云，分类全部本地完成。
- 交付包不含 API 密钥，不含第三方原始文件与训练中间产物。

## 已知限制

- 事务类短信召回率当前 0.9568，未达到 98% 硬指标。
- 当前验收口径仅中文；英文、印地语、印尼语为架构预留，尚无正式评测。
- 性能数据为模拟器工程测量，不代表真机结果。

## 交付物清单

- Demo APK：`02_Android/app-debug.apk`（SHA256 `5374914c54f4...`）。
- SDK AAR：`02_Android/classifier-sdk-release.aar`（SHA256 `fc4245852962...`）。
- 端侧模型：`01_模型/sms_bytecnn_int8.tflite`。
- 指标与审计：`05_指标报告/`、`06_审计与合规/`。

## 参考文档

- 最终验收报告：`00_验收报告/最终验收报告.md`
- 数据说明：`04_训练与数据/data/README-数据.md`
- Gradle 构建说明：`02_Android/android-src/README-GRADLE.md`