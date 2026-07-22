#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add missing 46 annotations to batch 4."""

import json

OUT_PATH = r"C:\Users\WOSHIN~1\AppData\Local\Temp\opencode\annotations_batch4.json"

with open(OUT_PATH, 'r', encoding='utf-8') as f:
    annotations = json.load(f)

missing = {
    'ccf9c3dcb620': {'label': 'AD', 'reason': '碧桂园花园+48万元+4层别墅+88923333'},
    '15890ac21a76': {'label': 'AD', 'reason': 'V+零号男+3周年+5折封顶+vjia.com'},
    '84e4c44bb68f': {'label': 'AD', 'reason': '信达东湾半岛+手机看房+城央绝版亲水豪宅'},
    'bfe284ab785e': {'label': 'TRANSACTION', 'reason': '快递到达收发室+取快递'},
    'd2ce0fadb768': {'label': 'HARASS', 'reason': '代开深圳广告/运输/贸易/建筑发票'},
    'e924730d40a2': {'label': 'NEEDS_REVIEW', 'reason': '城市向东+未来向东+70-140平+13406116662'},
    'd45111c383b3': {'label': 'HARASS', 'reason': '佰库网+十二星座+诱导'},
    '48785402dafd': {'label': 'AD', 'reason': '惠通陆华+捷豹路虎+二手车置换'},
    '6ee95d17252e': {'label': 'AD', 'reason': '颐和高尔夫庄园+千平果岭+养生山墅+86059168'},
    '899a1b5d7bf8': {'label': 'NEEDS_REVIEW', 'reason': '券商收盘版投资建议'},
    '66251fe3ac03': {'label': 'TRANSACTION', 'reason': '阿里旅行+199元机票直减券过期'},
    '3aa8c400b6cc': {'label': 'AD', 'reason': '兴宏程建造师+苏州+68291311'},
    'de4ca8faae46': {'label': 'HARASS', 'reason': '华夏基金学员+建仓300223+必涨5%'},
    'e8ed8f1a30f0': {'label': 'AD', 'reason': '喜达华庭+12%年收益+增值回购+02862030999'},
    '7007d09c17a5': {'label': 'TRANSACTION', 'reason': '小三美日+订单+78780820'},
    'd1559d8c17d8': {'label': 'TRANSACTION', 'reason': '微信电话本验证码'},
    '3975263df896': {'label': 'TRANSACTION', 'reason': '支付宝付款校验码'},
    '2b75c92b40f8': {'label': 'NEEDS_REVIEW', 'reason': '券商投资建议'},
    '32c74b84cde7': {'label': 'HARASS', 'reason': '银达基金+300223+强势拉升'},
    'f98d6891766f': {'label': 'AD', 'reason': '建业贰号城邦+装饰艺术园林+69168888'},
    'dac3cf7f8ad5': {'label': 'AD', 'reason': '移动+5月惠民+1999元+三星8268'},
    'c5b902896f74': {'label': 'AD', 'reason': '易信+高清语音+免费短信+yixin.im'},
    '6c961b053e51': {'label': 'AD', 'reason': '工行+禧享外惠+结售汇+七折点差'},
    '71b5d8ce1d1a': {'label': 'AD', 'reason': '丰收蟹庄+野生大闸蟹+420元/斤'},
    '6fc9b5602aee': {'label': 'AD', 'reason': '惠生活+桂林+厦门鼓浪屿+1780元'},
    '288266c1df4c': {'label': 'AD', 'reason': '山东事业单位+2小时速成+962823869'},
    'c0df3b304bf9': {'label': 'NEEDS_REVIEW', 'reason': '韩国女歌手+诱导图片'},
    '127d1de49735': {'label': 'TRANSACTION', 'reason': '广发卡取现+1000元'},
    '8790910b63d0': {'label': 'AD', 'reason': '8号公馆+门票19元+按摩18元'},
    'ce7d4eba3a87': {'label': 'AD', 'reason': '正阳东郡+60-130平+6100元/平'},
    '914200e9b1ec': {'label': 'AD', 'reason': '双色球+9+3专家推荐'},
    'cdd00872ea4a': {'label': 'NEEDS_REVIEW', 'reason': '券商收盘版投资建议'},
    '4d779f58ab48': {'label': 'TRANSACTION', 'reason': '快钱验证码+尾号2511+268元'},
    'e6b73b9a0271': {'label': 'AD', 'reason': '联通流量抽奖+20元充值卡+iPad mini'},
    '73c030c0b4a3': {'label': 'NEEDS_REVIEW', 'reason': '券商收盘版投资建议'},
    'ec409abe9b57': {'label': 'AD', 'reason': '尚学堂+中考名师+400-040-7797'},
    '091e02241a82': {'label': 'AD', 'reason': '麦考林+520+4折+M18.com'},
    '4c56edaa101f': {'label': 'HARASS', 'reason': '硕士+专科申硕+15300257686'},
    '3264a824a5ce': {'label': 'TRANSACTION', 'reason': '去哪儿网+HU7601+报销凭证'},
    '53fd7f370a69': {'label': 'AD', 'reason': '易通全联+汽配会+010-65533297'},
    'cb61e4420334': {'label': 'TRANSACTION', 'reason': '去哪儿网+KN5819+在线选座'},
    '8850b6abb026': {'label': 'NEEDS_REVIEW', 'reason': '女性文章+健康+减肥诱导'},
    'd62b2750845e': {'label': 'AD', 'reason': '携程+酒店促销+99元'},
    '8e85dcd666e7': {'label': 'HARASS', 'reason': '快融+无担保+借款+028-66003939'},
    'ee7d8285f319': {'label': 'TRANSACTION', 'reason': '招行信用卡退款+405.50元'},
    'b15fc3e97245': {'label': 'AD', 'reason': '歌皇KTV+啤酒+18626284444'},
}

annotations.update(missing)

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(annotations, f, ensure_ascii=False, indent=2)

print(f'Batch 4 final: {len(annotations)} annotations')
