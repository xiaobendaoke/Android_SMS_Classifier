# Model Card

> 阶段 0 占位。模型就绪后填写。

- 架构：Byte-level TextCNN（学生）、bert-base-multilingual-cased（教师，仅训练机）
- 输入：512 UTF-8 bytes，token ID 1..256，PAD=0
- 输出：`[TRANSACTION, AD, HARASS, FRAUD]`
- 量化：INT8 PTQ（必要时 QAT）
