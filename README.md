# Android 终端侧离线短信分类识别系统

端侧离线四分类短信识别 Demo App + 可复用 SDK（AAR）+ 训练/蒸馏/剪枝/量化流水线。

## 主规格文档

实施与验收以仓库根目录主规格为准：

- [Android终端侧离线短信分类识别系统-完整实施与最终审核方案.md](./Android终端侧离线短信分类识别系统-完整实施与最终审核方案.md)

## 项目结构

| 目录 | 说明 |
|------|------|
| `android/` | Gradle 多模块：app、classifier-sdk、benchmark |
| `training/` | Python 数据与模型训练流水线 |
| `tools/` | 发布审核、SBOM、合规检查脚本 |
| `docs/` | 架构、标注、隐私、测试与报告文档 |
| `reports/` | 指标、基准、审核与发布报告输出目录 |

## 环境要求

- Python ≥ 3.8
- JDK 17+（Android 构建）
- Android SDK（API 34，minSdk 26）
- Gradle Wrapper（见 `android/README-GRADLE.md`）

**换机测试前必读：** [docs/异机测试环境安装清单.md](./docs/异机测试环境安装清单.md)  
（本仓库框架可在弱虚拟机维护；完整编译、训练、真机验收在其他电脑安装组件后进行。）

## Make 目标

```bash
make help                 # 列出所有目标
make setup-python         # 创建虚拟环境并安装锁定依赖
make audit-data           # 数据来源审计
make prepare-data         # 构建数据集
make train-baseline       # 训练 n-gram 基线
make train-teacher        # 微调多语 BERT 教师
make distill              # 蒸馏 Byte TextCNN 学生
make prune                # 结构化通道剪枝
make quantize             # INT8 量化
make verify-model         # Keras/TFLite 一致性验证
make evaluate             # 冻结测试集评测
make export-android-assets # 导出模型与规则到 SDK assets
make android-test         # Android 单元/仪器化测试
make android-build        # 构建 Debug APK
make benchmark            # 真机性能基准（仪器化）
make audit-release        # 发布前合规审核
make package-release      # 打包发布产物
```

## 快速验证（轻量，本机可做）

```bash
PYTHONPATH=training python3 -m pytest training/tests -q
python3 tools/check_no_network_permission.py
```

Android 构建与训练链请按 [异机测试环境安装清单](./docs/异机测试环境安装清单.md) 在开发机/训练机执行。

## 约束

- App 与 SDK **不得**申请 `INTERNET` 权限
- 原始短信数据不入 Git（见 `training/data/README.md`）
- 不自动永久删除短信；疑似垃圾可恢复

## 许可证

Apache License 2.0 — 见 [LICENSE](./LICENSE) 与 [NOTICE](./NOTICE)。
