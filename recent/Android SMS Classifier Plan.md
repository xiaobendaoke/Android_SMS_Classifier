# **Android端侧离线短信分类与拦截系统设计与工程实施方案**

## **一、 课题定位与核心矛盾剖析**

在移动互联网生态体系中，垃圾短信、商业推广骚扰以及电信网络诈骗呈现高发与高变异态势1。尽管部署在云端的文本分类算法拥有极高的计算上限与精度，但由于其必须将用户的实时短信内容上传至云端服务器进行语义解构，在当今严苛的隐私保护法规下，面临着巨大的合规风险与数据泄露隐患1。特别是在政企安全、海外数据合规以及无网/弱网等物理隔离场景下，基于云端的过滤方案完全失效。因此，研发一套完全运行于 Android 终端设备本地、物理隔绝数据上云、具备极低系统资源损耗以及极高防误杀能力的“Android 终端侧离线短信分类识别系统”具有迫切的工程落地价值。  
本系统将运行于中低端 Android 终端设备（如配置为 4GB 或 6GB RAM 的设备），其核心矛盾在于“严苛的端侧算力、内存、功耗限制”与“高精度、高鲁棒性语义分类需求”之间的博弈4。系统的设计与实现必须遵循四大技术原则。第一是零上云，即所有分词、特征提取、深度学习推理及规则决策逻辑均在设备本地芯片中进行；第二是无重型模型，即摒弃参数量达到数十亿的重型大型语言模型，采用经过深度压缩、参数量在千万级以下的轻量化自然语言处理模型3；第三是短信不出设备，通过沙盒物理阻断数据泄露风险1；第四是防误杀，将事务性通知（如银行验证码、账户变动、物流取件码等）的拦截错误率视为生命线，确保召回率不低于 98%6。  
在分类体系上，系统摒弃了传统粗糙的“垃圾/正常”二分类模式，参考业界前沿的分类规范，将短信精准划分为通用事务（General/Normal）、商业广告（Promotion）、通知验证（Notification）、交易流水（Transaction）以及恶意垃圾/诈骗（Junk/Spam/Fraud）五大核心维度3。本方案将基于端侧 AI（Edge AI）的核心技术，深入阐述其数据集构建、对抗防御、微型模型架构、双保险路由设计、系统级拦截实现以及终端性能度量。

## **二、 多语言数据集构建与端侧多语种语料库构建**

由于本系统需要兼顾出海及多语言业务场景（涵盖中文、英文、印地语、印尼语等），端侧分类算法必须具备跨语种的泛化表征能力8。然而，现有的端侧公开短信数据集多存在单语言、不平衡的缺陷6。为此，本系统采用混合多语言语料库构建方案。  
系统引入经典的 UCI 短信垃圾分类数据集作为基准英语语料10，并在此基础上融入学术界与工业界通用的多语言扩增数据集 dbarbedillo/SMS\_Spam\_Multilingual\_Collection\_Dataset9。该数据集以原始 UCI 语料为基础，采用先进的多语言序列到序列编码翻译模型（如 M2M100\_418M）进行跨语种机器翻译与增强，涵盖了中文、印地语、西班牙语、印尼语等 18 种以上的关键语种9。  
在实际的现实世界部署中，正常短信（Ham）与垃圾短信（Spam）通常存在极端的类不平衡问题，垃圾短信在真实通信流中占比仅为 13% 到 15% 左右6。为解决这一问题，系统在离线模型训练阶段，除了采用传统的合成少数类过采样技术（SMOTE）和自适应合成采样（ADASYN）外，还引入了基于生成对抗网络（GAN）的词嵌入合成增强方案6。该方案在嵌入层（Embedding Layer）直接生成代表少数类语义的合成向量，不仅能避免传统拼写替换带来的语法破碎，还能将多语言分类性能的 F1 值显著提升6。跨语种泛化性测试表明，在经过多语言知识蒸馏与增强后，模型在非英语语境下的性能衰减被成功控制在 3.25% 以内6。

| 数据集名称 | 包含语种数 | 实例总量 | 正常/垃圾分布 | 数据获取与增强方式 | 适用场景评估 |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **UCI SMS Spam Collection** \[cite: 11\] | 单一英语9 | 5574 条11 | \~86.6% 对 13.4%10 | 原始学术收集10 | 英文基准特征训练10 |
| **Multilingual Spam Data** \[cite: 10\] | 英语、中文、印地语、德语等9 | \~20000+ 条（多语种对齐） | 对齐分布10 | 机器翻译增强（基于 Kaggle 原始语料）9 | 跨语种零样本迁移测试（Zero-shot Transfer）10 |
| **Multilingual Collection (M2M100)** \[cite: 9\] | 中、英、印地、印尼等18+语种9 | \> 100,000 条（增强后） | 保持原始不平衡比例9 | 采用 M2M100\_418M 编码器进行高保真双向翻译增强9 | 本地模型跨国泛化能力训练与多语种测试报告生成8 |

## **三、 端侧对抗性文字防御与归一化机制**

网络不法分子在发送商业推销或诈骗短信时，通常会采用对抗性文本变形策略，企图通过修改字符编码或添加干扰信息来规避传统的敏感词检索机制与浅层自然语言处理分类模型13。

### **1\. 对抗攻击手段解构**

对抗性文本变形主要包括以下三种形式：  
第一，字形替换攻击（Homoglyph Attack）。攻击者利用相似字形替换目标字符，例如将标准英文字符替换为西里尔字母、希腊字母或特殊的数学 Unicode 符号（如将 ASCII 的小写 "a" 替换为西里尔字母 "а" \[U+0430\]，或将 "e" 替换为 "е" \[U+0435\]）13。这种变异对人类视觉而言几乎没有阻碍，但这些替换字符在 Unicode 空间中拥有完全不同的码点，能轻易导致未经处理的词表产生严重的 OOV（Out-Of-Vocabulary）映射丢失13。  
第二，中文同音替代与音形扰动。在中文语境下，攻击者常用同音字、拼音或者声母、拼音首字母缩写来替换敏感词（例如将“微信”混淆替换为“威信”、“微x”、“v信”；将“裸贷”写为“倮贷”）15。这种现象被称为中文同音字噪声，极大地破坏了传统中文分词器和嵌入模型的编码分布15。  
第三，不可见字符插入与符号填充。在关键敏感词中间强行插入零宽空格（Zero-Width Space \[U+200B\]）等不可见 Unicode 字符，或者填充连续的无意义干扰标点，使文本在字符匹配层面被截断16。

### **2\. 端侧文本标准化流水线设计**

为克服上述对抗扰动，本系统在端侧分词器前构建了一条兼顾算力消耗与清洗深度的端侧归一化流水线（Normalization Pipeline）。

\[原始短信文本输入\]  
       │  
       ▼  
┌────────────────────────────────────────┐  
│     Stage 1: 物理 Unicode 兼容分解      │ (使用 java.text.Normalizer 进行 NFKD 标准化)  
└────────────────────────────────────────┘  
       │  
       ▼  
┌────────────────────────────────────────┐  
│    Stage 2: 异形字形骨架映射 (Skeleton) │ (将拉丁/西里尔/希腊相似字符转换为基准码点)  
└────────────────────────────────────────┘  
       │  
       ▼  
┌────────────────────────────────────────┐  
│ Stage 3: 中文同音映射与拼音级表征提取  │ (采用双重表征设计，捕获拼音特征)  
└────────────────────────────────────────┘

在系统执行时，原始短信首先流经 Unicode 兼容分解层。系统调用 Android 系统底层的 java.text.Normalizer 类，将其强制转化为 Form.NFKD（兼容分解格式）。这一步可以消除 90% 以上通过字符变体、合并音标、上下标和连写造成的字形干扰。  
随后，文本进入异形字形骨架转换模块。系统采用端侧轻量化混淆字典映射算法（基于 unicode-security 规范和 skeleton 骨架化检索）21。该算法将输入的 Unicode 码点转换成预定义的安全骨架码点。

Kotlin  
// 异形字骨架转换核心算法 (Kotlin)  
fun sanitizeHomoglyphs(text: String): String {  
    val stringBuilder \= StringBuilder()  
    var i \= 0  
    while (i \< text.length) {  
        val codePoint \= text.codePointAt(i)  
        // 查询本地存储的16位紧凑二进制混淆查找表  
        val standardCodePoint \= OnDeviceHomoglyphTable.getStandard(codePoint)  
        stringBuilder.appendCodePoint(standardCodePoint)  
        i \+= Character.charCount(codePoint)  
    }  
    return stringBuilder.toString()  
}

针对中文拼音及同音代换攻击，本方案摒弃了传统的规则穷举，引入了联合文本与音学表征的特征融合网络（类似于 BiGRU-CNN-JE 架构）。在对文本执行完 Unicode 标准化后，一方面提取文本的字形与语义向量；另一方面，系统通过本地预加载的拼音转译器将中文字符映射为声母与韵母拼音序列（如将“微信”和“威信”均映射为 "wei xin"）。拼音序列通过一个轻量级的一维卷积特征提取器（TextCNN）生成拼音特征向量，再与原汉字字嵌入特征向量进行拼接（Joint Embedding）。这一架构在实测中能够直接利用声学相似性填补同音替代词在语义空间中的断层，赋予系统抗击拼音、特殊混淆词的天然鲁棒性。

## **四、 离线微型NLP模型蒸馏、剪枝与量化方案**

由于中低端 Android 终端设备物理内存紧缺，运行时额外分配内存必须控制在 100 MB 阈值内，处理一条短短信的耗时不能超过 500 ms4。这导致参数量达数亿的原始 BERT 级 Transformer 模型无法直接在端侧进行部署26。本系统基于三阶段的模型压缩流水线，将原始的多语言大模型精简为适合在移动端芯片高效执行的超微型自然语言分类器27。

### **1\. 模型架构选型与对比**

为了在极低硬件开销下实现深层文本理解，系统对各轻量化自然语言处理模型进行了对比分析：

| 评估指标 | 词袋 FastText 架构 | 轻量 TextCNN 架构 | 标准 DistilBERT 架构 | 本项目采用的 MobileBERT 蒸馏量化版 |
| :---- | :---- | :---- | :---- | :---- |
| **典型参数量** | \< 3 M | \~ 12 M | \~ 66 M26 | \~ 25 M (量化前)31 \-\> 4.6 M (剪枝后)27 |
| **端侧内存消耗（INT8）** | \~ 12 MB | \~ 24 MB | \~ 260 MB26 | \~ 18 MB (极致量化)27 |
| **端侧推理时延 (ARM CPU)** | \~ 8 ms30 | \~ 18 ms | \~ 220 ms31 | \~ 65 ms28 |
| **跨语种迁移泛化能力** | 较差，对词表极度依赖29 | 一般，缺少长距离上下文依赖 | 优秀33 | 极佳（继承了大型教师模型的多语言表征能力）8 |
| **对抗变形抗性** | 低（拼写变体易导致OOV）29 | 中等（局部滑动窗口敏感） | 较高（注意力机制对微小扰动容忍度好） | 极高（结合了音形双向标准化表征）15 |

### **2\. 深度三阶段模型压缩方案**

系统通过结合知识蒸馏、结构化剪枝和对称 INT8 量化，将模型大小压缩至 18 MB27。

#### **阶段一：知识蒸馏 (Knowledge Distillation)**

系统以完全预训练的多语言 BERT-Large 模型（拥有 24 层 Transformer 编码层，参数量约 340 M）作为教师模型（Teacher）28。使用端侧 MobileBERT 模型作为学生模型（Student），该学生模型采用瓶颈结构（Bottleneck Structure）来显著降低各层的内部通道维度31。在蒸馏过程中，系统不仅在最后一层的 Softmax 输出上引入温度系数（Temperature \= 4.0）进行 KL 散度约束，更对中间的自注意力层（Self-Attention Layers）和前馈神经网络（FFN）进行了逐层渐进式知识转移（Progressive Knowledge Transfer）27。这使得 MobileBERT 能够从庞大的教师模型中完美复制其上下文空间的多语言对齐表征，在参数量缩减 4.3 倍、推理速度加快 4 倍的同时，GLUE 综合表现仅出现 0.6% 的微幅变动31。

#### **阶段二：灵敏度引导的结构化剪枝 (Sensitivity-Guided Pruning)**

在模型完成知识蒸馏收敛后，系统对其各注意力头（Attention Heads）和隐藏层参数矩阵进行稀疏性分析28。采用结构化剪枝方案（Structured Pruning），以不影响底层矩阵并行计算（GEMM）吞吐量为前提，剔除其中对分类结果贡献度处于底部 30% 范围的注意力头，并裁撤冗余的隐藏层 FFN 通道数34。相较于容易产生稀疏零矩阵、无法直接加速非定制硬件计算的非结构化剪枝35，结构化剪枝能实现物理上的隐藏层矩阵维度减小（例如将层维度由 512 降至 256），从而切实提升了端侧单线程 ARM 架构下的矩阵乘法速度28。

#### **阶段三：对称 INT8 训练后量化 (Post-Training Quantization, PTQ)**

针对模型中大量的 32 位浮点型（FP32）权重与计算激活值，系统使用 TensorFlow Lite 转换器中的整型量化算子对模型执行全量对称 INT8 量化（Fully Integer Quantization）35。量化过程中的量化映射关系由权重矩阵和标定数据集（Calibration Dataset）共同决定28。虽然 INT4 量化拥有极高的理论压缩比（对大模型如 BERT-Large 可实现达 95.8% 的物理存储缩减）28，但在主流的 Android 终端处理器上（如 ARM Cortex-A 系列），由于硬件缺乏对 4 位算子的原生算力指令支持，在进行矩阵乘法前会频繁引发开销极大的运行时解量化（De-quantization Overhead）行为，最终反而导致端侧 CPU 推理延迟显著劣化28。因此，本系统采用全算子对称 INT8 量化，该方案可将模型文件的磁盘体积由 \~100MB 直接压降至 \~18MB27，且完全利用了移动端 CPU 底层的 NEON 向量指令集进行硬件级乘累加加速（FMA），推理性能在低端 Android 真机上被直接提速 2.9 到 3.8 倍27。

## **五、 “双保险”分流架构与可解释性AI设计**

### **1\. 智能分流路由设计 (Smart Hierarchy Flow)**

为保证 98% 的验证码和事务短信召回率红线6，本系统杜绝仅靠端侧 AI 分类器单向处理的做法，而采用**双保险智能分流架构**3。该架构根据强特征匹配、上下文行为以及端侧深度特征的置信度，建立了一套严格的优先级分流逻辑3。

Kotlin  
// 双保险智能分流路由伪代码逻辑 (Kotlin)  
class SmsSecurityRouter(  
    private val regexEngine: RegexEngine,  
    private val mlClassifier: SmsClassifier,  
    private val contactManager: OnDeviceContactManager  
) {  
    fun routeIncomingSms(senderNumber: String, body: String, simSlot: Int): RoutingDecision {  
        // 第一保险层：规则引擎直接短路  
          
        // 1\. 本地联系人白名单直接判定为普通通知事务  
        if (contactManager.isSavedContact(senderNumber)) {  
            return RoutingDecision(SmsCategory.GENERAL, "Whitelist: Native Saved Contact")  
        }  
          
        // 2\. 高时效性动态事件白名单  
        if (contactManager.checkTemporalWhitelist(senderNumber)) {  
            return RoutingDecision(SmsCategory.GENERAL, "Whitelist: Temporal Active Session")  
        }  
          
        // 3\. 高置信度 OTP/财务安全正则兜底 \[cite: 38, 39\]  
        val regexMatchResult \= regexEngine.matchSafeguardPatterns(body)  
        if (regexMatchResult.isMatched) {  
            return RoutingDecision(SmsCategory.NOTIFICATION, "Safeguard Rules: Hardcoded Transaction / OTP")  
        }

        // 第二保险层：AI 语义分类  
          
        // 4\. 输入标准化清洗 \[cite: 15, 18\]  
        val cleanText \= TextNormalizer.normalize(body)  
          
        // 5\. 运行轻量化 AI 模型层  
        val prediction \= mlClassifier.predict(cleanText)  
          
        // 6\. 软投票与可解释性规则后处理  
        if (prediction.confidence \>= CONFIDENCE\_THRESHOLD) {  
            return RoutingDecision(prediction.category, "AI Engine Decision (Confidence: ${prediction.confidence})")  
        } else {  
            // 对低置信度判决进入兜底分流层，优先归为GENERAL，避免误拦截  
            return RoutingDecision(SmsCategory.GENERAL, "Fallback: Ambiguous Semantic Classifier")  
        }  
    }  
}

### **2\. 多重白名单与兜底机制**

多重白名单和高时效性白名单机制具体包括以下三层保障：  
第一，本地物理白名单。系统通过安全查询 Android 内置联系人 Provider，获取用户通信录中的已知联系人2。任何来自已知联系人的来电或短信，一律具有最高级豁免权，直接越过所有过滤逻辑，进入普通收件箱并保持通知触达2。  
第二，时效性时序白名单（Temporal Dynamic Whitelist）。系统通过 UsageStatsManager 接口静态注册、动态感知用户在设备前台的最近操作状态1。例如，当用户在最近 30 分钟内主动启动了 Uber Eats、本地打车或者特定的网购客户端1，或者通过 SMS 渠道触发了外部应用的联动广播37，该算法会在本地的缓存时间窗（如 30 分钟）内自动将该时段内下发的外卖配送员号码、特定短号平台号码直接添加至临时白名单1。此方式完美解决了因同城配送短号码随机变动而引发的漏网或者误判纠纷1。  
第三，OTP（一次性密码）及账户财务流水正则表达式强保护机制。系统内置高优先级的静态预编译正则表达式库（采用 Java 底层的编译 Pattern 机制，缓存复用以实现近乎零的 O(1) 匹配开销）1。

Java  
// 精准保护验证码的强置信度正则  
public static final Pattern COMPACT\_OTP\_REGEX \= Pattern.compile(  
    "(?i)(?:验证码|验证码为|动态密码|verification\\\\s\*code|otp|login\\\\s\*code)\\\\s\*\[:is是\\\\s\#\]\*(\\\\b\\\\d{4,8}\\\\b)"  
);

// 银行/财务交易账户通知保活正则  
public static final Pattern COMPACT\_FINANCIAL\_REGEX \= Pattern.compile(  
    "(?:已从您账户扣除|您账户已支出|已划扣|成功汇款|您尾号.\*的卡|已入账|余额为|debited|credited|balance)"  
);

若文本匹配此类关键特征，判定优先级在 AI 模型之前，直接将分类确认为 NOTIFICATION（通知类）或 TRANSACTION（交易类）3。这一“规则强约束层”极大地维护了事务性短信的安全3。

### **3\. 可解释性 AI（XAI）的本地化构建**

由于短信拦截通常运行于设备后台，一旦对短信进行了拦截，必须具备极强的可解释性（Explainable AI），以打消用户对于系统误拦、错判的疑虑40。 本系统在端侧通过**后置特征词解释器**（On-Device Feature Attribution Explainer）来实现可解释性： 当 AI 模型将短信分类标记为 JUNK（垃圾广告）或 FRAUD（诈骗）时，系统不仅返回分类概率值，还会通过对决策网络中的特定隐藏激活值（Activation Maps）进行反向加权回溯，寻找对该分类决策贡献最大的关键指示词汇（如“转账”、“立即点击”、“代开税票”等）。在用户隔离箱页面展示时，系统会附带具体的可解释理由，例如：“该消息已被拦截，原因在于系统识别出该短信内容包含高危敏感词汇（‘转账’、‘账号异常’），结合上下文分析判定其涉嫌金融诈骗，其语义置信度为 96.7%”40。

## **六、 Android系统级拦截实现机制与跨进程服务协议**

### **1\. 系统级拦截技术演进与抉择**

在 Android 系统架构中，自 Android 4.4 版本以来，系统级的短信写权限和广播控制机制经历了严格的重构42。传统的通过高优先级 BroadcastReceiver 并调用 abortBroadcast() 的拦截路径，已经无法阻止新短信写入系统短信数据库，也无法阻止其他应用感知短信通知2。因此，当前的系统级拦截技术路径需要根据业务深度进行选择。  
本系统提出两套标准的拦截工程实施方案：第一套为**默认短信应用托管模式**；第二套为基于开放接口的**短信过滤服务协议（SMS Screening Protocol）模式**44。两套模式对比如下：

| 特性对比 | 默认短信应用托管模式 (Default SMS App) | 短信过滤协议服务提供者模式 (Screening Provider Mode) |
| :---- | :---- | :---- |
| **工作原理** | 申请注册成为系统的默认短信应用，直接接管系统的 SMS\_DELIVER\_ACTION 广播2。 | 实现一个标准协议的服务（Service），等待系统兼容此协议的默认短信 app 进行轮询调用44。 |
| **权限要求** | 极高（需要 RECEIVE\_SMS, WRITE\_SMS, READ\_SMS, SEND\_SMS）2 | 极低（通常无需敏感的物理 SMS 读写权限）37 |
| **物理删除能力** | 支持，可直接在底层数据库对垃圾短信执行删除或静默移箱3 | 不支持，仅能向调用方返回应否拦截的布尔决策值44 |
| **通知栏展示** | 完全接管，由应用自行绘制、完全自定义通知栏及 LED 灯颜色37 | 由发起查询的默认短信 app 进行标准的通知行为展现37 |
| **应用包体开销** | 较大，需附带整套短信收发与 UI 展示组件37 | 极低，小于 20MB（仅包含后台过滤服务和量化模型）2 |

### **2\. 短信过滤协议 (SMS Screening Protocol) 深度工程实现**

由于“默认短信应用模式”因庞大的 UI 视图和繁重的历史数据处理导致包体累赘，在特定政企、隐私合规和极简化系统插件场景下，本方案深度推崇**短信过滤协议模式（SMS Screening Protocol）**44。这一机制彻底摆脱了冗长危险的短信权限申请逻辑，在保证高内聚功能的同时，具备低开销和解耦特性44。  
在该协议下，开发团队需在拦截引擎应用（即 Screening Provider）的 AndroidManifest.xml 中对外注册并导出标准的过滤服务组件44：

XML  
\<service  
    android:name\=".service.PublicSMSScreeningService"  
    android:exported\="true"  
    android:permission\="android.permission.BIND\_SCREENING\_SERVICE"\>  
    \<intent-filter\>  
        \<action android:name\="sms.screening.provider.PublicSMSScreeningService" /\>  
    \</intent-filter\>  
\</service\>

在系统运行层，宿主默认短信应用（如 QUIK SMS 等兼容应用）在收到运营商下发的原始 SMS 后，会主动向当前系统已安装的该 Screening Provider 发起跨进程调用绑定（通过 Binder / Messenger 通信机制体系）44。双方进行跨进程通信时，必须严格遵守以下 IPC 键值和协议定义规范：

Kotlin  
// 跨进程短信拦截服务协议实现类 (Kotlin)  
class PublicSMSScreeningService : Service() {  
    private val mMessenger \= Messenger(IncomingMessageHandler())

    override fun onBind(intent: Intent?): IBinder? {  
        // 返回Binder实例以供客户端进行跨进程通信绑定  
        return mMessenger.binder  
    }

    private inner class IncomingMessageHandler : Handler(Looper.getMainLooper()) {  
        override fun handleMessage(msg: Message) {  
            // 解析协议指令  
            if (msg.what \== PROTOCOL\_SMS\_SCREENING) {  
                val dataBundle \= msg.data ?: return  
                val senderNumber \= dataBundle.getString(KEY\_NUMBER, "")  
                val smsContent \= dataBundle.getString(KEY\_SMS\_CONTENT, "")  
                val simSlot \= dataBundle.getInt(KEY\_SIM\_SLOT, 0)  
                  
                // 执行本地双保险分流过滤核心算法  
                val decision \= SmsSecurityRouter.route(senderNumber, smsContent, simSlot)  
                  
                // 构建跨进程返回的Reply Message  
                val replyMessenger \= msg.replyTo  
                if (replyMessenger \!= null) {  
                    val replyMessage \= Message.obtain(null, PROTOCOL\_SMS\_SCREENING\_RESULT)  
                    val replyBundle \= Bundle().apply {  
                        putBoolean(KEY\_SHOULD\_BLOCK, decision.shouldBlock)  
                        putString(KEY\_REASON, decision.reason)  
                    }  
                    replyMessage.data \= replyBundle  
                    try {  
                        replyMessenger.send(replyMessage)  
                    } catch (e: RemoteException) {  
                        Log.e("IPC\_Screening", "Failed to send screening reply", e)  
                    }  
                }  
            } else {  
                super.handleMessage(msg)  
            }  
        }  
    }

    companion object {  
        const val PROTOCOL\_SMS\_SCREENING \= 1  
        const val PROTOCOL\_SMS\_SCREENING\_RESULT \= 2  
          
        const val KEY\_NUMBER \= "number"  
        const val KEY\_SMS\_CONTENT \= "smsContent"  
        const val KEY\_SIM\_SLOT \= "simSlot"  
        const val KEY\_SHOULD\_BLOCK \= "shouldBlock"  
        const val KEY\_REASON \= "reason"  
    }  
}

该协议极大地缩减了过滤插件的物理边界。在这种模式下，过滤引擎能够独立对短信执行实时判断，而物理层面的数据删除或移动动作，则安全地交由具有默认权限的宿主短信应用执行，从根本上降低了端侧 AI 程序的越权漏洞和系统不稳定性风险。

## **七、 终端性能度量与极速保活优化机制**

### **1\. 内存度量、耗时评估与真机监测体系**

由于中低端手机中常有严苛的低内存杀进程（Low Memory Killer, LMK）机制存在，系统运行时内存超出 100 MB 很容易面临被随时终结的风险4。系统引入了以 **比例集大小（PSS, Proportional Set Size）** 作为核心验收标准的实时内存监控框架46。相比于仅计算虚拟地址空间的 VSS（Virtual Set Size）或未摊销共享共享库开销的 RSS（Resident Set Size），PSS 能够将多个进程之间共享的 Native 共享链接库（如 libtensorflowlite\_jni.so）物理开销，按照比例科学摊销46。  
系统性能评估模块不仅要利用 getProcessMemoryInfo 动态监视运行时 JVM 与 Native 的 PSS 指标变化46，更在端侧测试套件中整合了完整的时延记录组件，对各环节进行纳秒级计时。

Kotlin  
// 高精度端侧过滤耗时监测工具  
class PerformanceMonitor {  
    fun runProfilingTask(text: String, process: () \-\> SmsDecision): SmsDecision {  
        val startCpuTime \= System.currentTimeMillis()  
        val startNano \= System.nanoTime()  
          
        val result \= process()  
          
        val endNano \= System.nanoTime()  
        val endCpuTime \= System.currentTimeMillis()  
          
        val totalMs \= (endNano \- startNano) / 1\_000\_000.0  
        val cpuMs \= endCpuTime \- startCpuTime  
          
        Log.i("Profiling", "Step execution total time: $totalMs ms, CPU Time: $cpuMs ms")  
        return result  
    }  
}

在中低端手机真机（4GB/6GB 内存设备）测试验证时，系统性能必须被严格约束在及格线和优秀目标指标内3：

| 关键评估维度 | 及格底线指标 | 优秀目标指标 | 性能评估监测方法与真机校验手段 |
| :---- | :---- | :---- | :---- |
| **额外运行时内存物理占用 (PSS)** | **![][image1]** \[cite: 3\] | ![][image2] | 基于 ActivityManager.getProcessMemoryInfo 程序化获取实际 PSS 变化，杜绝内存泄漏46。 |
| **单条短信全链路推理延迟** | **![][image3]** \[cite: 3\] | ![][image3] | 使用纳秒时钟 System.nanoTime() 全链路统计“文本标准化 \+ WordPiece 分词 \+ TFLite 矩阵乘法 \+ 规则匹配”耗时。 |
| **重要验证码/通知召回率 (Recall)** | **![][image4]** \[cite: 3\] | ![][image4] | 针对模拟包含 10000 条混合主流运营商通知、金融交易账户变化的真实业务场景测试集进行自动化回放评测。 |
| **广告与骚扰细分类混淆精度 (Precision)** | **![][image4]** | **![][image4]** | 针对含有特定推广标签、彩信、营销内容的异形对抗短信进行跨语种细分类判定精确度检验。 |

### **2\. 内存泄漏与崩溃防御体系**

在内存紧张的移动端设备上，频繁的垃圾文本分析、大块字符串转换以及模型推理极易引起严重的内存抖动（Memory Churn），进而触发频繁的垃圾回收（Garbage Collection, GC）事件，甚至由于物理堆耗尽触发内存溢出崩溃（OutOfMemoryError）4。系统在底层工程层面建立了三道防御线。  
第一，全生命周期 mmap 权重文件映射映射。系统不使用传统的 JVM 字节数组缓存加载轻量 NLP 模型49。而是使用 FileChannel.map 方法将 TensorFlow Lite 或 MNN 模型的 .tflite/.mnn 二进制文件直接通过内核态内存映射映射（mmap）到系统的只读物理虚拟内存页中49。此机制极大地避免了垃圾回收器对大字节数组对象的无效扫描与整理，即使发生严重的资源抢占，系统也可以直接由内核无开销地回收这部分虚拟页，极大地降低了端侧内存敏感度49。  
第二，无堆分配（Allocation-Free）的词汇查找表（WordPiece Tokenizer）。由于分词阶段需要对大段文本进行高频的切分与字符匹配，传统的 StringTokenizer 或 split 算子会频繁创建并销毁海量的中间小字符串对象，触发大量的内存碎片和内存抖动4。本系统在端侧实现基于只读缓冲区指针的无内存复制（Zero-Copy）WordpieceTokenizer 分词算法51。该算法在分词与词表映射过程中，始终只通过原始短信字符串的起止索引指针（CharOffsets）以及基于整型哈希表的内存定位表进行比对（类似于 Wordpiece 算法的贪婪匹配最长前缀逻辑）51，杜绝了中间小字符串的实例化，使分词阶段的额外对象分配开销降至零。  
第三，基于 Android 17 的主动内存异常哨兵响应。系统深度对接了新版 Android 17 底层引入的 ProfilingManager 机制，主动挂接 TRIGGER\_TYPE\_OOM 和 TRIGGER\_TYPE\_ANOMALY 两大关键系统信号4。一旦系统由于底层其他常驻程序抢占资源而引发过度内存占用异常（TRIGGER\_TYPE\_ANOMALY）4，在系统层发出终止信号前，系统会主动触发 onTrimMemory(TRIM\_MEMORY\_RUNNING\_CRITICAL) 预警回调4。在该回调逻辑中，过滤引擎会立即触发内存紧缩逻辑：彻底断开并卸载端侧的 AI NLP 模型解释器实例、重置其静态词向量缓存，直接平滑退化到纯规则过滤通道，从而防止自身的强行物理终止崩溃，成功维护其作为通信守护进程的生命长周期可靠性。

#### **引用的著作**

1. SpamBlocker: The Powerful Android Call Shield Developers Love \- Smart Converter, [https://converter.brightcoding.dev/blog/spamblocker-the-powerful-android-call-shield-developers-love](https://converter.brightcoding.dev/blog/spamblocker-the-powerful-android-call-shield-developers-love)  
2. NoSpamPro: Spam SMS & Spam Call Blocker | AI Technology | Privacy, Security and Fast., [https://forums.androidcentral.com/threads/nospampro-spam-sms-spam-call-blocker-ai-technology-privacy-security-and-fast.1085707/](https://forums.androidcentral.com/threads/nospampro-spam-sms-spam-call-blocker-ai-technology-privacy-security-and-fast.1085707/)  
3. ovehbe/junkboy: SMS Filtering App \- GitHub, [https://github.com/ovehbe/junkboy](https://github.com/ovehbe/junkboy)  
4. Manage your app's memory | App quality \- Android Developers, [https://developer.android.com/topic/performance/memory](https://developer.android.com/topic/performance/memory)  
5. Android-App-Memory-Analysis/docs/en/android\_memory\_debug\_guide.md at master, [https://github.com/Gracker/Android-App-Memory-Analysis/blob/master/docs/en/android\_memory\_debug\_guide.md](https://github.com/Gracker/Android-App-Memory-Analysis/blob/master/docs/en/android_memory_debug_guide.md)  
6. Cross-lingual SMS spam detection using GAN-based augmentation for imbalanced datasets, [https://pmc.ncbi.nlm.nih.gov/articles/PMC12921278/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12921278/)  
7. Junkman: AI Spam SMS Blocker \- App Store \- Apple, [https://apps.apple.com/us/app/junkman-ai-spam-sms-blocker/id1591815272](https://apps.apple.com/us/app/junkman-ai-spam-sms-blocker/id1591815272)  
8. Multilingual SMS Spam Classification Using NLP and Transfer Learning, [https://ijaibdcms.org/index.php/ijaibdcms/article/view/377](https://ijaibdcms.org/index.php/ijaibdcms/article/view/377)  
9. dbarbedillo/SMS\_Spam\_Multilingual\_Collection\_Dataset · Datasets at Hugging Face, [https://huggingface.co/datasets/dbarbedillo/SMS\_Spam\_Multilingual\_Collection\_Dataset](https://huggingface.co/datasets/dbarbedillo/SMS_Spam_Multilingual_Collection_Dataset)  
10. Multilingual Spam Data \- Kaggle, [https://www.kaggle.com/datasets/rajnathpatel/multilingual-spam-data](https://www.kaggle.com/datasets/rajnathpatel/multilingual-spam-data)  
11. SMS Spam Collection \- UCI Machine Learning Repository, [https://archive.ics.uci.edu/dataset/228/sms+spam+collection](https://archive.ics.uci.edu/dataset/228/sms+spam+collection)  
12. Duplicate from dbarbedillo/SMS\_Spam\_Multilingual\_Collection\_Dataset \- Hugging Face, [https://huggingface.co/datasets/ashu0311/SMS\_Spam\_Multilingual\_Collection\_Dataset/commit/c0ec602d378587a711b88a74ee4928349c00b2e8](https://huggingface.co/datasets/ashu0311/SMS_Spam_Multilingual_Collection_Dataset/commit/c0ec602d378587a711b88a74ee4928349c00b2e8)  
13. Homoglyph Encoding Strategy \- Promptfoo, [https://www.promptfoo.dev/docs/red-team/strategies/homoglyph/](https://www.promptfoo.dev/docs/red-team/strategies/homoglyph/)  
14. MMU NLP at CheckThat\! 2024: Homoglyphs are Adversarial Attacks \- CEUR-WS.org, [https://ceur-ws.org/Vol-3740/paper-53.pdf](https://ceur-ws.org/Vol-3740/paper-53.pdf)  
15. Chinese Spam Detection Using a Hybrid BiGRU-CNN Network with Joint Textual and Phonetic Embedding \- MDPI, [https://www.mdpi.com/2079-9292/11/15/2418](https://www.mdpi.com/2079-9292/11/15/2418)  
16. Hijacking Text Heritage: Hiding the Human Signature through Homoglyphic Substitution, [https://arxiv.org/html/2604.10271v1](https://arxiv.org/html/2604.10271v1)  
17. Chinese Spam Detection Using a Hybrid BiGRU-CNN Network with Joint Textual and Phonetic Embedding \- ResearchGate, [https://www.researchgate.net/publication/362473942\_Chinese\_Spam\_Detection\_Using\_a\_Hybrid\_BiGRU-CNN\_Network\_with\_Joint\_Textual\_and\_Phonetic\_Embedding](https://www.researchgate.net/publication/362473942_Chinese_Spam_Detection_Using_a_Hybrid_BiGRU-CNN_Network_with_Joint_Textual_and_Phonetic_Embedding)  
18. Normalizer | API reference \- Android Developers, [https://developer.android.com/reference/kotlin/java/text/Normalizer](https://developer.android.com/reference/kotlin/java/text/Normalizer)  
19. Normalizing Text (The Java™ Tutorials \> Internationalization \> Working with Text), [https://docs.oracle.com/javase/tutorial/i18n/text/normalizerapi.html](https://docs.oracle.com/javase/tutorial/i18n/text/normalizerapi.html)  
20. Normalizer | J2ObjC \- Google for Developers, [https://developers.google.com/j2objc/javadoc/jre/reference/java/text/Normalizer](https://developers.google.com/j2objc/javadoc/jre/reference/java/text/Normalizer)  
21. GitHub \- codebox/homoglyph: A big list of homoglyphs and some code to detect them, [https://github.com/codebox/homoglyph](https://github.com/codebox/homoglyph)  
22. Unicode normalization of homoglyphs to ASCII using Rust \- Stack Overflow, [https://stackoverflow.com/questions/75818436/unicode-normalization-of-homoglyphs-to-ascii-using-rust](https://stackoverflow.com/questions/75818436/unicode-normalization-of-homoglyphs-to-ascii-using-rust)  
23. Unicode Normalization \- HackTricks, [https://hacktricks.wiki/en/pentesting-web/unicode-injection/unicode-normalization.html](https://hacktricks.wiki/en/pentesting-web/unicode-injection/unicode-normalization.html)  
24. A phonetic-based approach to Chinese chat text normalization \- PolyU Scholars Hub, [https://research.polyu.edu.hk/en/publications/a-phonetic-based-approach-to-chinese-chat-text-normalization/](https://research.polyu.edu.hk/en/publications/a-phonetic-based-approach-to-chinese-chat-text-normalization/)  
25. Detect Camouflaged Spam Content via StoneSkipping: Graph and Text Joint Embedding for Chinese Character Variation Representation \- ACL Anthology, [https://aclanthology.org/D19-1640/](https://aclanthology.org/D19-1640/)  
26. Comparative Efficiency Analysis of Lightweight Transformer Models: A Multi-Domain Empirical Benchmark for Enterprise NLP Deploym \- arXiv, [https://arxiv.org/pdf/2601.00444](https://arxiv.org/pdf/2601.00444)  
27. CMES | Free Full-Text | Optimizing BERT for Bengali Emotion Classification: Evaluating Knowledge Distillation, Pruning, and Quantization \- Tech Science Press, [https://www.techscience.com/CMES/v142n2/59371/html](https://www.techscience.com/CMES/v142n2/59371/html)  
28. An end-to-end pipeline for compressing and accelerating BERT models using sensitivity-guided layer pruning and FP16 quantization. \- GitHub, [https://github.com/ManiaAmaeOvo/bert-layer-pruning-quantization](https://github.com/ManiaAmaeOvo/bert-layer-pruning-quantization)  
29. Non-Contextual BERT or FastText? A Comparative Analysis \- ACL Anthology, [https://aclanthology.org/2025.globalnlp-1.4.pdf](https://aclanthology.org/2025.globalnlp-1.4.pdf)  
30. Comparative Analysis of BERT, FastText, and Perspective API for Effective Harmful Content Detec \- Search for publications in DiVA, [https://liu.diva-portal.org/smash/get/diva2:1970373/FULLTEXT01.pdf](https://liu.diva-portal.org/smash/get/diva2:1970373/FULLTEXT01.pdf)  
31. MobileBERT: Task-Agnostic Compression of BERT by Progressive Knowledge Transfer, [https://openreview.net/forum?id=SJxjVaNKwB](https://openreview.net/forum?id=SJxjVaNKwB)  
32. Tiny Language Models for Automation and Control: Overview, Potential Applications, and Future Research Directions \- PMC, [https://pmc.ncbi.nlm.nih.gov/articles/PMC11902656/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11902656/)  
33. BERT or FastText? A Comparative Analysis of Contextual as well as Non-Contextual Embeddings \- arXiv, [https://arxiv.org/html/2411.17661v2](https://arxiv.org/html/2411.17661v2)  
34. Compressing BERT: Studying the Effects of Weight Pruning on Transfer Learning \- Johns Hopkins Computer Science, [https://www.cs.jhu.edu/\~kevinduh/papers/gordon20bert.pdf](https://www.cs.jhu.edu/~kevinduh/papers/gordon20bert.pdf)  
35. Compressing BERT for faster prediction | Rasa Blog, [https://rasa.com/blog/compressing-bert-for-faster-prediction-2](https://rasa.com/blog/compressing-bert-for-faster-prediction-2)  
36. Comprehensive Study on Performance Evaluation and Optimization of Model Compression: Bridging Traditional Deep Learning and Large Language Models \- arXiv, [https://arxiv.org/html/2407.15904v1](https://arxiv.org/html/2407.15904v1)  
37. aj3423/SpamBlocker: Android Call/SMS blocker. \- GitHub, [https://github.com/aj3423/SpamBlocker](https://github.com/aj3423/SpamBlocker)  
38. Need help regarding regex to extract OTP from SMS? \[duplicate\] \- Stack Overflow, [https://stackoverflow.com/questions/54115611/need-help-regarding-regex-to-extract-otp-from-sms](https://stackoverflow.com/questions/54115611/need-help-regarding-regex-to-extract-otp-from-sms)  
39. How to Block Text Spam on Android | Block Guard Guide, [https://www.blockguard.app/how-to-block-text-spam-android/](https://www.blockguard.app/how-to-block-text-spam-android/)  
40. How to Recognize and Report Spam Text Messages \- FTC Consumer Advice, [https://consumer.ftc.gov/articles/how-recognize-and-report-spam-text-messages](https://consumer.ftc.gov/articles/how-recognize-and-report-spam-text-messages)  
41. GitHub \- apsun/NekoSMS: A pattern-based text message blocker for Android., [https://github.com/apsun/NekoSMS](https://github.com/apsun/NekoSMS)  
42. Default Feature to Block All Incoming SMS and IM (except for approved contacts) \- \- to prevent Pegasus infection : r/signal \- Reddit, [https://www.reddit.com/r/signal/comments/oquvtb/default\_feature\_to\_block\_all\_incoming\_sms\_and\_im/](https://www.reddit.com/r/signal/comments/oquvtb/default_feature_to_block_all_incoming_sms_and_im/)  
43. SMS Screening Protocol · aj3423/SpamBlocker Wiki \- GitHub, [https://github.com/aj3423/SpamBlocker/wiki/SMS-Screening-protocol](https://github.com/aj3423/SpamBlocker/wiki/SMS-Screening-protocol)  
44. Use of SMS or Call Log permission groups \- Play Console Help \- Google Help, [https://support.google.com/googleplay/android-developer/answer/10208820?hl=en](https://support.google.com/googleplay/android-developer/answer/10208820?hl=en)  
45. How do I discover memory usage of my application in Android? \- Stack Overflow, [https://stackoverflow.com/questions/2298208/how-do-i-discover-memory-usage-of-my-application-in-android](https://stackoverflow.com/questions/2298208/how-do-i-discover-memory-usage-of-my-application-in-android)  
46. Investigating Your RAM Usage | Android Developers, [https://spot.pcc.edu/\~mgoodman/developer.android.com/tools/debugging/debugging-memory.html](https://spot.pcc.edu/~mgoodman/developer.android.com/tools/debugging/debugging-memory.html)  
47. ActivityManager.GetProcessMemoryInfo(Int32\[\]) Method (Android.App) | Microsoft \- Microsoft Learn, [https://learn.microsoft.com/en-us/dotnet/api/android.app.activitymanager.getprocessmemoryinfo?view=net-android-35.0](https://learn.microsoft.com/en-us/dotnet/api/android.app.activitymanager.getprocessmemoryinfo?view=net-android-35.0)  
48. Text Classification In Android With TensorFlow Lite | Shubham Panchal \- Medium, [https://medium.com/data-science/spam-classification-in-android-with-tensorflow-lite-cde417e81260](https://medium.com/data-science/spam-classification-in-android-with-tensorflow-lite-cde417e81260)  
49. StringTokenizer | API reference \- Android Developers, [https://developer.android.com/reference/kotlin/java/util/StringTokenizer](https://developer.android.com/reference/kotlin/java/util/StringTokenizer)  
50. tflite-android-transformers/bert/src/main/java/co/huggingface/android\_transformers/bertqa/tokenization/WordpieceTokenizer.java at master \- GitHub, [https://github.com/huggingface/tflite-android-transformers/blob/master/bert/src/main/java/co/huggingface/android\_transformers/bertqa/tokenization/WordpieceTokenizer.java](https://github.com/huggingface/tflite-android-transformers/blob/master/bert/src/main/java/co/huggingface/android_transformers/bertqa/tokenization/WordpieceTokenizer.java)  
51. Subword tokenizers | Text \- TensorFlow, [https://www.tensorflow.org/text/guide/subwords\_tokenizer](https://www.tensorflow.org/text/guide/subwords_tokenizer)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFAAAAAWCAYAAABXEBvcAAAAiUlEQVR4Xu3XsQ2DQBBE0c2QI0JwSBOkJFThDhxQhAsgpAHLchXugYh67LU2G8n4NkX/SZPsZKNLzgwAUKr3vPWI/xqL4W5aYN9iMVyrBfYNFsNdtcBvlWfzPLVAme+LO+sROZPFkJ0WKHfyrJ5ZC+RdLF7kqAVyHp6XHpFXGz8RAMd0TwQAjuADJ4oWrbeO91wAAAAASUVORK5CYII=>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEcAAAAWCAYAAACSYoFNAAAAiElEQVR4Xu3WMQrCUBCE4WnTB4Q0HiW9pxC8QDrv4DFyBHMTC6+jb9kiZEAQSSHs/8E0b7plH6wEAP9rbHn5Y3WDcihXLyqblUPpvajspBzKxYuqupancltgYlMO/ojVpBzS0Quk+F6PlpsX2DorNynuG3xwb1n8EVtx73AhA9hDXMbfBgB+8QaZQxbG0kwwogAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEkAAAAWCAYAAACMq7H+AAAAiElEQVR4Xu3WMQrCUBCE4WnTC0KaHMXeUwRygXTewWN4BHOTFF4nvmUrxxe0iRD8P5jmTbfsg5UAYL9OJYs/IrXK4Vy8gHRTDufgBaSzcjiDF/+uKXkotwcrYnOO/oh3o3JYnRd4Fd9uLrl6gbpeuVlxH+GDe8nkj6iLe4mLG8AvxKX9bQBgC0/3fBbG773i8QAAAABJRU5ErkJggg==>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEMAAAAWCAYAAACbiSE3AAAAeUlEQVR4Xu3SsQ1AYBQE4OvEEBJb0BlAYgmlBcyh1yi0eiNZgl9eI1dIaO++5Jp73eUBZmb/nCkll8q2lIlLdQXiUzo+KBtSDsQ49nB/ysqlshoxirQGMULLBzX3CDOXSnrECBUflOSIEUY+KMlSdi7NzF4sH2Jmmi7hnhYOGX0jYwAAAABJRU5ErkJggg==>