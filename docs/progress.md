# 项目进度

> 每次阶段验收后更新：已完成项、命令、结果、遗留问题。

## 当前状态

**框架代码已搭好（弱虚拟机）** — 不在本机做 Android SDK 全量构建、BERT 训练与真机验收。  
异机安装与验证步骤见：[异机测试环境安装清单.md](./异机测试环境安装清单.md)

## 已完成

### 框架 / SDK

- [x] 目录树与 Makefile / README / LICENSE / NOTICE
- [x] `classifier-sdk`：NFKC 归一化、ByteEncoder、JSON 规则引擎、DecisionRouter、无模型降级
- [x] 规则资产：otp / transaction / fraud / ad + confusables + model_metadata
- [x] JVM 单测用例（OTP、冲突→REVIEW、Hindi、byte 一致性）— **需异机装 SDK 后跑 Gradle**
- [x] Manifest 无 `INTERNET`

### App 框架

- [x] ROLE_SMS 资格组件与申请页
- [x] `SmsDeliverReceiver`：先写系统 Provider 再分类、超时 REVIEW
- [x] Room 仅存分类元数据（无正文）
- [x] Compose：收件箱 / 疑似垃圾 / 复核 / 评测 / 性能 / 关于

### 训练流水线框架

- [x] 合成 JSONL 样例（四语四类）
- [x] audit / build / validate / baseline / evaluate（numpy 可跑）
- [x] teacher / distill / prune / quantize / verify（缺 TF 时 exit 2 + 提示）
- [x] `requirements-train.txt` 重依赖清单

### 文档与工具

- [x] [异机测试环境安装清单.md](./异机测试环境安装清单.md)
- [x] `tools/audit_release.py` 等审核脚本骨架

## 命令记录（本机）

| 日期 | 命令 | 结果 |
|------|------|------|
| 2026-07-14 | `PYTHONPATH=training python3 -m pytest training/tests -q` | 通过（历史记录：10+ passed） |
| 2026-07-14 | `./gradlew :classifier-sdk:test` | 失败：本机无 Android SDK（预期） |

## 遗留问题（异机关闭）

1. 配置 `android/local.properties` 后执行 `./gradlew test assembleDebug`
2. 安装 `training/requirements-train.txt` 后跑完整蒸馏量化链，导出 `.tflite`
3. 4GB/6GB 真机性能与默认短信闭环验收
4. 冻结测试集事务召回达标后再宣称指标 PASS
