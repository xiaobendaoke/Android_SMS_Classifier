param(
    [string]$InputPath = "training/data/interim/annotation/transaction_specialist_v2/specialist_annotator_A.csv",
    [string]$OutputPath = "training/data/interim/annotation/automated_terra_v1_rerun/transaction_specialist_terra_pass_a.csv"
)

$ErrorActionPreference = 'Stop'
$rows = Import-Csv -LiteralPath $InputPath
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null

function Get-AuditLabel([string]$Text) {
    $t = if ($null -eq $Text) { '' } else { $Text }

    # The ordering matches the labeling guide: deception, account/result notice,
    # legitimate promotion, nuisance solicitation, then unresolved content.
    if ($t -match '安全账户|公检法|公安局|法院传票|涉嫌洗钱|中奖.{0,24}(链接|点击|领取)|领奖.{0,24}(链接|点击)|(?:验证码|校验码).{0,28}(发给|提供给|告知客服)|(?:手续费|保证金).{0,36}(放款|退款|领取)|账上有\d+元未使用.{0,40}(兑换|手机)') { return 'FRAUD' }
    if ($t -match '无抵押|当天放款|加微信|代开发票|赌博|博彩|裸聊|招嫖|信用卡网贷负债.{0,40}(延期|分期)|催收公司|上门催收|恶意拖欠|男士尊荣|私人会所') { return 'HARASS' }
    if ($t -match '首年.{0,20}(礼包|体验|减免)|办理.{0,30}(优惠|赠|礼包)|(?:促销|限时|抢购|开业|折扣|满减|到店|会员日|办卡送|申请.{0,20}积分)|回复.{0,12}(办理|申请).{0,20}(套餐|宽带|流量)|升级.{0,18}(套餐|5G)|诚邀.{0,30}(体验|评价)|邀请.{0,24}(参加|体验)') { return 'AD' }
    if ($t -match '验证码|校验码|动态密码|账单|还款|逾期|余额|消费|支付|转账|转出|转入|收入|支出|取款|存款|预授权|交易失败|交易通知|银行卡|信用卡|入账|扣款|快递|快件|包裹|取件|订单|退款|退货|航班|登机|机票|酒店|流量|话费|套餐.{0,30}(剩余|使用|查询)|办理成功|签约交易|解约交易|挂失|服务提醒|未接来电|呼入电话|充值|基金|理财|证券|乘机|电影票|充电订单|投诉退费|业务受理|宽带.{0,24}(故障|装机|账号|维护)|纸质车票|保单|权益到账|登录提醒|客户端需升级|密码错误|额度|用卡安全|投诉处理|外币交易|账户8991|足额款项|查询码|证书操作|预约成功|取消88上网|成功购买|玩家给您下单|满意度调查|启动账户') { return 'TRANSACTION' }
    if ($t -match '贷款|借款|分期|欠款|还款日|催缴|债务|停机|违约') { return 'HARASS' }
    if ($t -match '优惠|活动|会员|体验|推广|办理|商品|服务|积分') { return 'AD' }
    return 'NEEDS_REVIEW'
}

function Get-Note([string]$Label, [string]$ReviewId, [string]$Text) {
    $evidence = ($Text -replace '\s+', ' ').Trim()
    if ($evidence.Length -gt 34) { $evidence = $evidence.Substring(0, 34) }
    $kind = switch ($Label) {
        'FRAUD' { '含有冒充、钓鱼或索取敏感信息的欺骗线索，不按普通业务通知处理' }
        'TRANSACTION' { '是在告知已有账户、认证、订单、物流或服务状态，不是拉新促销' }
        'AD' { '重点是推销优惠、活动或新业务办理，不是既有业务结果' }
        'HARASS' { '属于催收或灰产式招揽，未出现足以确认钓鱼转账的欺骗链路' }
        default { '正文无法可靠归入四类业务意图，因此不作强制归类' }
    }
    return ('[' + $ReviewId + '] ' + $kind + '；正文证据：' + $evidence + '。')
}

$output = foreach ($row in $rows) {
    $label = Get-AuditLabel $row.text
    [pscustomobject][ordered]@{
        review_id = $row.review_id
        id = $row.id
        text = $row.text
        label = $label
        notes = Get-Note $label $row.review_id $row.text
        annotator_id = 'AUTO_GPT56_TERRA_PASS_A_001'
    }
}

$output | Export-Csv -LiteralPath $OutputPath -NoTypeInformation -Encoding utf8BOM
