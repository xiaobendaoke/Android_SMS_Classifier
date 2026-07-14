# 架构说明

> 阶段 0 占位。详见主规格第 4 节总体架构。

- 收信 → 归一化 → 规则引擎 + Byte TextCNN INT8 → 分类/处置路由
- 正文仅在内存处理；Room 仅存 URI/ID 与分类元数据
- SDK 与 App 完全离线，无 `INTERNET` 权限
