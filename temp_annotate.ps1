$csvPath = "training/data/interim/annotation/transaction_specialist/transaction_specialist_annotator_A.csv"
$rows = Import-Csv -LiteralPath $csvPath

$annotatorId = "HUMAN_A_001"

# Define label map for first batch
$labelMap = @{
    "zh-n2w-00760" = "TRANSACTION"; "zh-n2w-00926" = "TRANSACTION"
    "zh-n2w-01001" = "TRANSACTION"; "zh-n2w-01047" = "TRANSACTION"
    "zh-n2w-01644" = "TRANSACTION"; "zh-n2w-01647" = "TRANSACTION"
    "zh-n2w-01723" = "AD"; "zh-n2w-01812" = "TRANSACTION"
    "zh-n2w-02079" = "TRANSACTION"; "zh-n2w-02499" = "TRANSACTION"
    "zh-n2w-02907" = "TRANSACTION"; "zh-n2w-03044" = "TRANSACTION"
    "zh-n2w-03172" = "TRANSACTION"; "zh-n2w-03191" = "TRANSACTION"
    "zh-n2w-03367" = "AD"; "zh-n2w-03657" = "TRANSACTION"
    "zh-n2w-03757" = "TRANSACTION"; "zh-n2w-04186" = "TRANSACTION"
    "zh-n2w-04320" = "TRANSACTION"; "zh-n2w-04550" = "NEEDS_REVIEW"
    "zh-n2w-05006" = "TRANSACTION"; "zh-n2w-05185" = "TRANSACTION"
    "zh-n2w-06440" = "TRANSACTION"; "zh-n2w-06597" = "TRANSACTION"
    "zh-n2w-07310" = "AD"; "zh-n2w-07663" = "TRANSACTION"
    "zh-n2w-07729" = "TRANSACTION"; "zh-n2w-08011" = "TRANSACTION"
    "zh-n2w-09077" = "AD"; "zh-n2w-09188" = "TRANSACTION"
    "zh-n2w-09405" = "TRANSACTION"
    "zh_00196" = "TRANSACTION"; "zh_00201" = "TRANSACTION"
    "zh_00211" = "TRANSACTION"; "zh_00230" = "TRANSACTION"
    "zh_00253" = "TRANSACTION"; "zh_00276" = "TRANSACTION"
    "zh_00372" = "TRANSACTION"; "zh_00668" = "TRANSACTION"
    "zh_00705" = "AD"; "zh_00713" = "NEEDS_REVIEW"
    "zh_00972" = "TRANSACTION"; "zh_01041" = "TRANSACTION"
    "zh_01043" = "TRANSACTION"; "zh_01109" = "TRANSACTION"
    "zh_01157" = "TRANSACTION"; "zh_01575" = "TRANSACTION"
    "zh_01645" = "TRANSACTION"; "zh_01978" = "TRANSACTION"
    "zh_02000" = "TRANSACTION"; "zh_02026" = "TRANSACTION"
    "zh_02210" = "TRANSACTION"; "zh_02342" = "TRANSACTION"
    "zh_02654" = "TRANSACTION"; "zh_02891" = "TRANSACTION"
    "zh_02904" = "TRANSACTION"; "zh_02931" = "AD"
    "zh_03052" = "TRANSACTION"; "zh_03201" = "TRANSACTION"
    "zh_03741" = "TRANSACTION"; "zh_03782" = "TRANSACTION"
    "zh_03847" = "TRANSACTION"; "zh_03894" = "TRANSACTION"
    "zh_04202" = "TRANSACTION"; "zh_04462" = "TRANSACTION"
    "zh_04573" = "AD"; "zh_04627" = "TRANSACTION"
    "zh_04635" = "AD"; "zh_05178" = "TRANSACTION"
    "zh_05233" = "TRANSACTION"; "zh_05259" = "TRANSACTION"
    "zh_05356" = "TRANSACTION"; "zh_05425" = "TRANSACTION"
    "zh_05433" = "TRANSACTION"; "zh_05477" = "TRANSACTION"
    "zh_05479" = "TRANSACTION"; "zh_05480" = "NEEDS_REVIEW"
    "zh_05544" = "TRANSACTION"; "zh_05633" = "TRANSACTION"
    "zh_05773" = "TRANSACTION"; "zh_05790" = "TRANSACTION"
    "zh_06403" = "TRANSACTION"; "zh_06433" = "TRANSACTION"
    "zh_06501" = "TRANSACTION"; "zh_06954" = "TRANSACTION"
    "zh_06999" = "TRANSACTION"; "zh_07041" = "TRANSACTION"
    "zh_07444" = "TRANSACTION"; "zh_07823" = "TRANSACTION"
    "zh_07973" = "AD"; "zh_08484" = "NEEDS_REVIEW"
    "zh_08579" = "TRANSACTION"; "zh_08831" = "AD"
    "zh_08894" = "TRANSACTION"; "zh_09138" = "TRANSACTION"
    "zh_09139" = "NEEDS_REVIEW"; "zh_09972" = "TRANSACTION"
    "zh_10386" = "AD"; "zh_10441" = "TRANSACTION"
    "zh_10868" = "AD"
}

$notesMap = @{
    "zh-n2w-04550" = "满意度调查，非四分类"
    "zh_00713" = "续短信内容不完整"
    "zh_05480" = "服务通知征求同意，非四分类"
    "zh_08484" = "仅查询余额，语义模糊"
    "zh_09139" = "错误提示，非四分类"
    "zh_10868" = "酒店推广链接"
}

foreach ($row in $rows) {
    $id = $row.id
    if ($labelMap.ContainsKey($id)) {
        $row.label = $labelMap[$id]
    } else {
        $row.label = "NEEDS_REVIEW"
    }
    $row.human_annotator_id = $annotatorId
    if ($notesMap.ContainsKey($id)) {
        $row.notes = $notesMap[$id]
    } else {
        $row.notes = ""
    }
}

$rows | Export-Csv -LiteralPath $csvPath -Encoding UTF8 -NoTypeInformation
Write-Host "Done processing $($rows.Count) rows. First batch complete."
