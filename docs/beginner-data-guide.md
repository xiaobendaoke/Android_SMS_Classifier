# 零基础数据准备手册（从今天开始）

> 目标：一步步做出可用于训练/验收的四分类短信数据。  
> 本手册对应仓库：`Android_SMS_Classifier`。  
> **禁止**把真实用户短信、含手机号/OTP 的私有正文上传公网 / Colab / Git。

---

## 0. 你现在处于哪一步

| 状态 | 说明 |
|------|------|
| 工程模型 | 已有 Colab 导出的演示模型（合成数据） |
| 验收数据 | **还没有**冻结真标测试集 |
| 今天目标 | 下载开源英文集 → 生成标注表 → 你开始人工标 50～500 条 |

---

## 1. 我已经帮你做好的事

1. 下载了 **UCI SMS Spam Collection**（官方学术开源）到：

```text
training/data/raw/uci_sms_spam/
  sms_spam_collection.zip
  extracted/SMSSpamCollection
  extracted/readme
```

2. 写好了「生成标注表」脚本：

```text
training/scripts/prepare_uci_annotation_pack.py
```

3. 空白标注模板：

```text
training/data/annotation_templates/annotation_blank.csv
```

> 原始短信文件在 `.gitignore` 里，**不会进 Git**（这是对的）。

---

## 2. 你现在按顺序做（复制命令即可）

### 步骤 A：打开 PowerShell，进入仓库

```powershell
cd "C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"
.\.venv\Scripts\activate
$env:PYTHONPATH = "training"
```

如果还没有虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -U pip
pip install -r training\requirements.lock
```

### 步骤 B：生成标注 Excel/CSV 包

```powershell
python training\scripts\prepare_uci_annotation_pack.py
```

成功后会生成（本地，默认不进 Git）：

```text
training/data/interim/annotation/
  uci_pilot_500.csv          ← 先标这个（约 500 条）
  uci_all_suggested.csv      ← 全量建议（以后再用）
  README_FOR_ANNOTATORS.txt
```

### 步骤 C：用 Excel / WPS 打开试点表

打开：`training\data\interim\annotation\uci_pilot_500.csv`

你会看到这些列：

| 列名 | 谁填 | 含义 |
|------|------|------|
| id | 不用改 | 样本编号 |
| text | 不用改 | 短信正文 |
| language | 不用改 | 目前是 `en` |
| source | 不用改 | 来源 id |
| uci_binary | 不用改 | 原来的 ham/spam |
| suggested_label | 参考 | 脚本猜的四类（**可错**） |
| suggest_reason | 参考 | 为什么这么猜 |
| **label** | **你填** | 最终标签 |
| **annotator** | **你填** | 你的名字 |
| template_group | 不用改 | 模板簇 id |
| notes | 可选 | 备注 |

### 步骤 D：怎么填 `label`（死记这个顺序）

与中文同一套主规格（**先诈骗，再事务**）。对每一条短信按序问：

1. 是不是在骗我？（假中奖、假账单领奖、钓鱼、要码要钱）→ `FRAUD`  
2. 是不是账户/订单/认证/物流等业务结果告知？→ `TRANSACTION`  
3. 是不是正规商家/内容服务促销（铃声订阅、手机优惠等）？→ `AD`  
4. 是不是成人/交友灰产/催收等骚扰（但不是典型诈骗）？→ `HARASS`  
5. 吃不准 / 私人闲聊 → `NEEDS_REVIEW`（不要硬猜，也**不要把 ham 硬塞成事务**）

短版说明：`training/data/interim/annotation/README_EN_ANNOTATORS.txt`  
完整版：`docs/labeling-guide.md`

合法取值只能是：

```text
TRANSACTION
AD
HARASS
FRAUD
NEEDS_REVIEW
```

### 步骤 E：今天最少完成多少

| 目标 | 数量 | 目的 |
|------|------|------|
| 今晚 | **50 条** | 练手，熟悉规则 |
| 本周 | **500 条（整张试点表）** | 英文试点完成 |
| 另找一人 | 同样 500 条独立再标一遍 | 算一致性（验收要求） |

两人标注时：

1. 复制两份文件，例如：  
   - `uci_pilot_500_alice.csv`  
   - `uci_pilot_500_bob.csv`
2. **不要互相看答案**
3. 标完后把不一致的拿出来讨论

---

## 3. SpamShield（你问的那个）怎么处理

地址：https://huggingface.co/datasets/M-Arjun/SpamShield-Datasets  

| 结论 | 说明 |
|------|------|
| 能用 | 主规格允许，标【第三方】，CC BY 4.0 |
| 我这边没法替你下完整包 | 需要你登录 Hugging Face 并点同意条款 |
| 现在先别下 | 等 UCI 试点标完再下，避免一次信息过载 |

等你 UCI 标完后，我再教你一步步申请、下载、映射 SpamShield。

---

## 4. 和「验收」的关系（避免走弯路）

- UCI 试点 = **练标注 + 英文训练补充**  
- **不是**冻结测试集  
- 冻结测试集以后要：四语、每类≥500、双人真标、单独冻结  

现在不要纠结「能不能一次过验收」，先把标注手感练出来。

---

## 5. 常见问题

**Q：suggested_label 能直接当答案吗？**  
A：不能。很多 ham 被标成 `NEEDS_REVIEW`，就是故意不让你自动当事务。

**Q：Excel 打开中文乱码？**  
A：脚本用了 `utf-8-sig`。若仍乱码：Excel → 数据 → 从文本/CSV → 选 UTF-8。

**Q：标错了怎么办？**  
A：改 `label` 列即可，保留 `notes` 说明。

**Q：能不能发给 ChatGPT 帮我标？**  
A：UCI 是公开研究数据，用于学习可以；但**私有真实短信不要发给公网 AI**。且冻结测试集最终仍要双人人工确认。

**Q：标完下一步做什么？**  
A：已提供转换与作业级训练入口（**非冻结验收**）：

```bash
make prepare-annotation-bootstrap
PYTHONPATH=training python training/scripts/distill_student.py \
  --config training/configs/student_homework_bootstrap.yaml --hard-only
```

说明见 `docs/homework-bootstrap-training-report.md`。冻结测试集仍需：四语、每类≥500、双人真标。

---

## 6. 今日检查清单（打勾）

- [ ] 能看到 `training/data/raw/uci_sms_spam/extracted/SMSSpamCollection`
- [ ] 跑通 `prepare_uci_annotation_pack.py`
- [ ] 打开 `uci_pilot_500.csv`
- [ ] 自己先标完 **50 条** `label` + `annotator`
- [ ] 找第二个标注人，准备独立再标一份

完成后回我：「50 条标完了」或贴遇到的具体报错（不要贴大量短信正文）。
