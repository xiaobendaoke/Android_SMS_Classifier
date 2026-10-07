# 数据说明（内部答辩用途）

> 本目录为交付包的数据快照：`train.jsonl`、`validation.jsonl`、`test.jsonl`。
> 仅限答辩/导师内部审核使用，禁止公开、上传或二次分发。

## 数据版本

| 文件 | 行数 | SHA256 |
|------|------|--------|
| `train.jsonl` | 11,095 | `aa8f71162ea1f5ff956afb38b0e42185db12e94d03310a6d097fb09a84f4717f` |
| `validation.jsonl` | 1,398 | `394916fa3506a565c451219c3b2590df9ca23188be6cf4d0e0fd1540e016d1d8` |
| `test.jsonl` | 1,397 | `d20f877b1718b93a5ea28f80dfb607fa0949b1666d12c57e906825e9cef25ee1` |

## 记录格式

每条记录字段：`id`、`text`、`label`、`language`、`source`、`source_license`、`sender_group`、`template_group`、`split`、`is_synthetic`、`is_adversarial`、`parent_id`。

- 四分类标签：`TRANSACTION` / `AD` / `HARASS` / `FRAUD`；另有少量 `NEEDS_REVIEW` 兜底样本。
- 验收口径为中文四分类；中文四分类行数：train 9,096 / validation 1,140 / test 1,125。

## 标签与语种分布

| 文件 | 标签分布 | 语种分布 |
|------|----------|----------|
| `train.jsonl` | TRANSACTION 3,403 / AD 4,773 / HARASS 1,238 / FRAUD 1,680 / NEEDS_REVIEW 1 | zh 9,097 / hi 801 / id 693 / en 504 |
| `validation.jsonl` | TRANSACTION 431 / AD 602 / HARASS 133 / FRAUD 214 / NEEDS_REVIEW 18 | zh 1,158 / hi 85 / id 85 / en 70 |
| `test.jsonl` | TRANSACTION 427 / AD 601 / HARASS 139 / FRAUD 230 | zh 1,125 / hi 104 / id 94 / en 74 |

## 来源与许可

| 来源 | 语种 | 许可 |
|------|------|------|
| `normal_2w_zh_relabel` | zh | 本地私有中文重标注数据，仅内部使用 |
| `gitcode_zh_sms_8a104` | zh | CC BY-NC-SA 4.0（研究用途） |
| `iiitd_sms_spam_v1` | hi/en-IN | 学术用途限定，不得超授权范围再分发 |
| `uci_sms_spam_collection_v1` | en | UCI 研究再分发条款 |
| `yudiwbs_id_sms_spam_v1` | id | CC BY-SA 4.0 |
| `spamshield_indonesian_v1` | id | CC BY 4.0 |

## 合规说明

- 本目录包含短信原文，可能含手机号、身份证号、银行卡号等 PII 样式 token；请勿截图外传、上传云盘或放入公开仓库。
- 本目录不含 API 密钥，也不包含第三方原始文件与训练中间产物。