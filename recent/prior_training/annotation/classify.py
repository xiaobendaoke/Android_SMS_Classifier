import json
import re

with open(r'C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier\training\data\interim\annotation\batch_1000_1699.json', 'r', encoding='utf-8') as f:
    records = json.load(f)

def classify(text):
    t = text.lower()
    
    # === FRAUD ===
    fraud_kw = ['won', 'winner', 'claim award', 'lottery', 'congratulations won',
                'number won', 'number selected', 'chevron', 'coca cola prize',
                'yahoo lottery', 'msn lottery', 'hot diamond', 'british diamond',
                'free car', 'selected 650,000', 'selected 700,000', 'selected 365,000',
                'selected 500,000', 'contact claim', 'email claim', 'claim contact',
                'claim email', 'ur number chosen', 'prize call rs', '/sms win rs',
                'rs /sms win', 'cocacolaclaim', 'msndept22', 'chevroinoil74',
                'britishdiamond', 'cocacolaprize', 'ticket to thailand',
                'extended till', 'qualifiars', '6.50lac', 'wfp', 'what your number',
                'get15grams', '15grams silver', 'won mobile', 'won phone',
                'won laptop', 'won bike', 'won car', 'won trip', 'won cash',
                'won gold', 'won silver', 'won diamond', 'won watch', 'won voucher',
                'prize worth', 'cash prize', 'prize winner', 'lucky draw winner',
                'lucky winner', 'congratulations! you are lucky',
                'congratulations!u have won', 'congratulations! you have won',
                'congratulations! u have won', 'congratulations on winning',
                'you have been awarded', 'you have been selected',
                'your number has won', 'your mobile number won',
                'your number has been awarded', 'your number has been selected',
                'your mobile number has won', 'your mobile number has been awarded',
                'your mobile number has been selected']
    for kw in fraud_kw:
        if kw in t:
            return 'FRAUD'
    
    # === Blyk interactive -> HARASS ===
    if re.search(r'reply within 24|reply.*24 hrs|reply.*24 hours|blyk|aircel.*free|all your replies.*free|all your interactions.*free|all your.*free.*blyk', t):
        return 'HARASS'
    
    # === TRANSACTION ===
    trans_kw = ['pnr', 'train detail', 'pnr status', 'policy due', 'premium due',
                'bill due', 'request timed out', 'code=', 'tid=', 'please complete registration',
                'settings delivered', 'mobile office active', 'recharge alert',
                'validity expired', 'data card expired', 'thanks for being a valued member',
                'thanks for being a member', 'thanks for your support', 'activate 3g',
                '3g activate', 'thanks for your support', 'Mobile Office active',
                'settings successfully', 'thanks for being', 'thanks for your',
                'you are enjoying', 'pack expires', 'you have been charged',
                'service has been activated', 'info call 121', 'dial 121',
                'balance information', '*121#', '*122*', '*123*5#',
                'thanks for being a valued member', 'thanks for your support',
                'thanks for being a member', 'thanks for your support',
                'thanks for being a valued member', 'thanks for your support',
                'thanks for being a member', 'thanks for your support',
                'thanks for being a valued member', 'thanks for your support',
                'thanks for being a member', 'thanks for your support']
    for kw in trans_kw:
        if kw in t:
            return 'TRANSACTION'
    
    # === HARASS ===
    harass_kw = ['work from home', 'earn per day', 'earn daily', 'earn per month',
                 'earn from home', 'income per day', 'income per month', 'per month income',
                 'part time income', 'full time income', 'rs. 15000', 'rs. 30000',
                 'rs 15000', 'rs 30000', 'mobile/laptop repairing', 'hi-tech se',
                 'per month', 'per day', 'daily income', 'monthly income',
                 'work from home earn', 'work from home&earn', 'work from home & earn',
                 'cyberjob', 'cyber job', '160by2', '160by2.com', 'sent 4rm',
                 'sent from', 'sent by', 'send your resume', 'email your resume',
                 'homejobsindya', 'home jobs', 'work at home', 'earn extra income',
                 'business opportunity', 'no investment', 'free joining',
                 'free training', 'natural aloe vera', 'bee honey',
                 'network marketing', 'mlm', 'franchise opportunity',
                 'rs. 15000/ se rs. 30000/', 'rs 15000/ se rs 30000/',
                 'rs. 15000/ se rs. 30000/', 'rs 15000/ se rs 30000/',
                 'rs. 15000/ se rs. 30000/', 'rs 15000/ se rs 30000/',
                 'rs. 15000/ se rs. 30000/', 'rs 15000/ se rs 30000/']
    for kw in harass_kw:
        if kw in t:
            return 'HARASS'
    
    # === AD ===
    ad_kw = ['talktime', 'recharge', 'full talktime', 'easycharge', 'easypack',
             'top up', 'rc', 'full talk time', 'fullest talktime', 'paper recharge',
             'full recharge', 'ka talktime', 'ka full', 'talktime validity',
             'din ke liye', 'din tak', 'din manya', 'recharge par',
             'full talktime rs', 'full talk time rs', 'talktime rs',
             'recharge alert', 'data card', 'datacard',
             'bhk', 'flat', 'plot', 'apartment', 'lac', 'lakh', 'sq.ft', 'sqft',
             'sq.yd', 'sqyd', 'property', 'properties', 'realty', 'developer',
             'project', 'launches', 'launch', 'possession', 'sector', 'noida',
             'gurgaon', 'faridabad', 'delhi', 'expressway', 'extn', '-extension',
             'x-way', 'xway', 'xprsway', 'xpressway', 'x-press', 'extension',
             'sec-', 'sector-', 'road', 'highway', 'nh-', 'nh8', 'golf course',
             'dwarka', 'sohna', 'manesar', 'greater noida', 'gamma', 'phi',
             'omega', 'alpha', 'beta', 'techzone', 'industrial', 'commercial',
             'retail', 'shop', 'office space', 'studio apartment', 'penthouse',
             'duplex', 'villa', 'floors', 'independent floor', 'plot for sale',
             'plot in', 'land', 'acres', 'acre', 'sq.mtr', 'sqm',
             'snapdeal', 'easemytrip', 'meru cab', 'merucabs', 'discount',
             'coupon', 'voucher', 'gift voucher', 'special offer', 'limited offer',
             'hurry', 'rush', 'deal', 'deals', 'cashback', 'money back',
             'flat 50%', 'flat 40%', 'flat 60%', '50% off', '40% off',
             '60% off', '80% off', '70% off', '30% off', '20% off',
             '90% off', '97% off', '94% off', '86% off', '83% off',
             'buy 1 get', 'buy 2 get', 'buy 3 get', 'buy one get',
             'free gift', 'free home delivery', 'free delivery',
             'flat ', '% off', '% discount', 'save upto', 'save rs',
             'worth rs', 'rs worth', 'only rs', 'just rs', 'starting rs',
             'from rs', 'rs onwards', 'rs only',
             'course', 'admission', 'registration open', 'apply now', 'mba',
             'training', 'certification', 'internship', 'college', 'university',
             'school', 'institute', 'academy', 'coaching', 'classes',
             'iit', 'aijee', 'cat', 'gate', 'gre', 'gmat', 'toefl', 'ielts',
             'ca classes', 'cpt', 'cs', 'icwa', 'mbbs', 'btech', 'mtech',
             'bsc', 'msc', 'ba', 'ma', 'bcom', 'mcom', 'phd', 'post graduate',
             'diploma', 'degree', 'graduation', 'post graduation',
             'hiring', 'walk-in', 'interview', 'career', 'placement',
             'telecaller', 'telecallers', 'call center', 'bpo', 'recruitment',
             'opening', 'position', 'job alert', 'job search', 'jobs',
             'vacancy', 'vacancies', 'walk in', 'walkin', 'fresher',
             'experience', 'salary', 'ctc', 'in hand', 'per annum',
             'lakh per', 'lakhs per', 'monthly salary', 'annual salary',
             'apply now', 'send resume', 'submit resume', 'post resume',
             'update resume', 'upload resume',
             'loan', 'home loan', 'car loan', 'emi', 'insurance',
             'credit card', 'debit card', 'investment', 'stock', 'ipo',
             'nfo', 'trading', 'share', 'mutual fund', 'fd', 'fixed deposit',
             'recurring deposit', 'rd', 'ppf', 'nss', 'kvp', 'mis',
             'post office', 'bank', 'hdfc', 'icici', 'sbi', 'axis',
             'kotak', 'standard chartered', 'citi', 'hsbc', 'baroda',
             'pnb', 'canara', 'syndicate', ' Vijaya', 'allahanda',
             'andhra', 'bank of india', 'central bank', 'union bank',
             'health', 'treatment', 'doctor', 'clinic', 'hospital',
             'weight loss', 'slim', 'height', 'herbal', 'ayurvedic',
             'medicine', 'medical', 'hairfall', 'hair loss', 'dental',
             'skin', 'asthma', 'allergies', 'obesity', 'diabetes',
             'hypertension', 'blood pressure', 'heart', 'kidney',
             'liver', 'thyroid', 'arthritis', 'cancer', 'tb', 'hiv',
             'aids', 'dengu', 'malaria', 'typhoid', 'jaundice',
             'pneumonia', 'bronchitis', 'sinus', 'migraine', 'headache',
             'fever', 'cold', 'cough', 'flu', 'virus', 'infection',
             'surgery', 'operation', 'therapy', 'checkup', 'check-up',
             'screening', 'test', 'diagnosis', 'x-ray', 'mri', 'ct scan',
             'ultrasound', 'ecg', 'eeg', 'blood test', 'urine test',
             'stool test', 'biopsy', 'vaccination', 'immunization',
             'homeopathy', 'allopathy', 'ayurveda', 'unani', 'siddha',
             'naturopathy', 'yoga', 'meditation', 'acupuncture',
             'physiotherapy', 'chiropractic', 'osteopathy',
             'holiday', 'trip', 'package', 'travel', 'flight', 'airline',
             'ticket', 'hotel', 'resort', 'tour', 'destination',
             'manali', 'shimla', 'goa', 'thailand', 'bangkok', 'dubai',
             'singapore', 'malaysia', 'bali', 'mauritius', 'maldives',
             'europe', 'australia', 'usa', 'uk', 'canada', 'new zealand',
             'south africa', 'kenya', 'tanzania', 'zimbabwe', 'zambia',
             'namibia', 'botswana', 'mozambique', 'madagascar',
             'seychelles', 'comoros', 'reunion', 'mayotte',
             'food', 'restaurant', 'dining', 'cafe', 'pizza', 'burger',
             'biryani', 'coffee', 'tea', 'drink', 'eat', 'meal', 'recipe',
             'cooking', 'kitchen', 'dinner', 'lunch', 'breakfast',
             'brunch', 'snack', 'dessert', 'sweet', 'cake', 'pastry',
             'bakery', 'cuisine', 'menu', 'buffet', 'thali',
             'movie', 'film', 'cinema', 'theater', 'theatre', 'music',
             'game', 'download', 'app', 'song', 'album', 'concert',
             'show', 'event', 'party', 'celebration', 'diwali',
             'christmas', 'rakhi', 'holi', 'new year', 'valentine',
             'eid', 'durga puja', 'ganesh chaturthi', 'navratri',
             'dussehra', 'janmashtami', 'makara sankranti', 'pongal',
             'onam', 'ugadi', 'gudi padwa', 'baisakhi', 'lohri',
             'bihu', ' Rath Yatra', 'ladoo', 'sweets', 'gifts',
             'cricket', 'football', 'hockey', 'tennis', 'badminton',
             'soccer', 'volleyball', 'basketball', 'baseball',
             'wrestling', 'boxing', 'golf', 'swimming', 'athletics',
             'service', 'repair', 'maintenance', 'cleaning', 'packers',
             'movers', 'courier', 'transport', 'logistics', 'construction',
             'renovation', 'interior', 'design', 'painter', 'plumber',
             'electrician', 'carpenter', 'mason', 'contractor',
             'architect', 'engineer', 'consultant', 'advisor',
             'lawyer', 'advocate', 'ca', 'chartered accountant',
             'company secretary', 'cost accountant', 'cs', 'icwa',
             'data card', 'datacard', '3g', '4g', 'internet', 'gprs',
             'sms pack', 'unlimited', 'call rate', 'tariff', 'roaming',
             'caller tune', 'callertune', 'ringtone', 'data plan',
             'broadband', 'wifi', 'wimax', 'airtel', 'vodafone',
             'idea', 'docomo', 'reliance', 'bsnl', 'mtnl', 'aircel',
             'tata', 'uninor', 'videocon', 'mts', 'loop', 'staline',
             'pen', 'pencil', 'pen drive', 'usb', 'headphone',
             'earphone', 'charger', 'battery', 'power bank', 'cable',
             'contest', 'competition', 'win mobile', 'win phone',
             'win laptop', 'win bike', 'win car', 'win trip',
             'win cash', 'win gold', 'win silver', 'win diamond',
             'win watch', 'win voucher', 'lucky draw', 'lucky winner',
             'lucky member', 'guess & win', 'guess and win',
             'answer and win', 'play and win', 'vote and win',
             'choose your option and win', 'choose option and win',
             'sms and win', 'call and win', 'dial and win',
             'participate and win', 'register and win',
             'subscribe and win', 'download and win',
             'offer', 'free', 'gift', 'bonus', 'reward', 'points',
             'cash', 'discount', 'save', 'best', 'top', 'new', 'latest',
             'trending', 'popular', 'hot', 'special', 'exclusive',
             'premium', 'luxury', 'quality', 'branded', 'original',
             'genuine', 'authentic', 'certified', 'approved',
             'guaranteed', 'assured', 'proven', 'tested', 'trusted',
             'recommended', 'rated', 'reviewed', 'awarded', 'recognized',
             'established', 'leading', 'number one', 'no.1', 'finest',
             'great', 'amazing', 'wonderful', 'fantastic', 'incredible',
             'awesome', 'superb', 'excellent', 'perfect', 'ideal',
             'ultimate', 'supreme', 'grand', 'mega', 'super', 'ultra',
             'extra', 'plus', 'max', 'pro', 'prime', 'select',
             'choice', 'preferred', 'favorite', 'favourite',
             'buy', 'sale', 'shop', 'store', 'book', 'booking',
             'call now', 'call me', 'call kare', 'call karo',
             'call now', 'sms now', 'sms today', 'limited offer',
             'limited period', 'limited time', 'hurry', 'rush',
             'deal', 'deals', 'special offer', 'special deal',
             'flat', '% off', '% discount', 'coupon', 'voucher',
             'gift voucher', 'free home', 'free delivery',
             'free shipping', 'cashback', 'cash back', 'money back',
             'moneyback', 'guarantee', 'guaranteed', 'assure', 'assured',
             'safe cure', 'safe treatment', 'fast cure', 'fast result',
             'world class', 'world famous', 'international',
             'premium', 'luxury', 'deluxe', 'exclusive', 'special',
             'limited edition', 'last chance', 'last day',
             'few units', 'few days', 'few hours', 'only few',
             'selling fast', 'selling out', 'book now', 'book today',
             'order now', 'order today', 'shop now', 'shop today',
             'buy now', 'buy today', 'get now', 'get today',
             'avail now', 'avail today', 'grab now', 'grab today',
             'claim now', 'claim today', 'redeem now', 'redeem today',
             'join now', 'join today', 'register now', 'register today',
             'sign up now', 'sign up today', 'subscribe now',
             'subscribe today', 'download now', 'download today',
             'install now', 'install today', 'try now', 'try today',
             'test now', 'test today', 'free now', 'free today']
    for kw in ad_kw:
        if kw in t:
            return 'AD'
    
    return 'NEEDS_REVIEW'

# Special cases override
special_cases = {
    'iiitd_01356': 'NEEDS_REVIEW',
    'iiitd_01473': 'NEEDS_REVIEW',
    'iiitd_01479': 'HARASS',
    'iiitd_01581': 'AD',
    'iiitd_01610': 'TRANSACTION',
}

# Generate reasons
def get_reason(text, label):
    t = text.lower()
    if label == 'FRAUD':
        if 'won' in t or 'winner' in t:
            return '假中奖诈骗，声称用户已中奖'
        if 'lottery' in t or 'prize' in t:
            return '虚假抽奖/奖品诈骗'
        if 'selected' in t and ('cash' in t or 'award' in t or 'prize' in t):
            return '虚假中奖，要求联系领取奖金'
        if 'chevron' in t or 'coca cola' in t or 'yahoo' in t or 'msn' in t:
            return '虚假公司名义中奖诈骗'
        if 'free car' in t:
            return '虚假免费汽车/房产诱惑'
        if 'ticket to thailand' in t or 'trip to thailand' in t:
            return '虚假旅游奖品诱导'
        if 'what your number' in t:
            return '虚假"你的号码"竞赛诈骗'
        if 'get15grams' in t or '15grams' in t:
            return '虚假银币奖励诱导'
        return '虚假中奖/奖品诈骗'
    elif label == 'TRANSACTION':
        if 'pnr' in t or 'train' in t:
            return 'PNR/列车信息查询服务'
        if 'policy' in t or 'premium' in t:
            return '保险保费到期通知'
        if 'bill' in t:
            return '账单到期通知'
        if 'request timed out' in t or 'code=' in t:
            return '服务请求超时/系统通知'
        if 'settings' in t or 'mobile office' in t:
            return '移动办公设置激活通知'
        if 'recharge alert' in t or 'validity' in t:
            return '充值/有效期到期提醒'
        if 'thanks' in t and ('member' in t or 'support' in t):
            return 'Blyk会员感谢消息'
        if 'activate' in t or '3g' in t:
            return '3G激活/服务通知'
        if 'balance' in t or '*121#' in t or '*123*' in t:
            return '账户余额/信息查询指引'
        if 'dial 121' in t or 'info call' in t:
            return '客服信息查询指引'
        if 'you are enjoying' in t or 'pack expires' in t:
            return '套餐到期提醒'
        if 'you have been charged' in t:
            return '扣费通知'
        if 'service has been activated' in t:
            return '服务激活确认'
        return '业务通知/服务消息'
    elif label == 'HARASS':
        if 'reply within 24' in t or 'blyk' in t or 'aircel' in t:
            return 'Blyk互动问答/骚扰式推销'
        if 'work from home' in t or 'earn' in t:
            return '高薪诱惑/在家工作诈骗'
        if '160by2' in t or 'cyberjob' in t:
            return '代发短信/网络兼职骚扰'
        if 'sent 4rm' in t or 'sent from' in t:
            return '代发短信骚扰'
        if 'business opportunity' in t or 'franchise' in t:
            return '商业机会/加盟骚扰'
        if 'no investment' in t or 'free joining' in t:
            return '零投资加盟诱惑'
        if 'natural aloe vera' in t or 'bee honey' in t:
            return '微商/保健品推销骚扰'
        if 'income' in t and ('month' in t or 'day' in t):
            return '高薪收入诱惑'
        if 'per month' in t or 'per day' in t:
            return '高薪诱惑'
        if 'rs. 15000' in t or 'rs. 30000' in t or 'rs 15000' in t or 'rs 30000' in t:
            return '高薪课程/工作诱惑'
        if 'mobile/laptop' in t or 'hi-tech' in t:
            return '高薪维修课程诱惑'
        if 'home jobs' in t or 'work at home' in t:
            return '在家工作诱惑'
        if 'send your resume' in t or 'email your resume' in t:
            return '简历收集骚扰'
        return '骚扰式推销/灰产'
    elif label == 'AD':
        if 'talktime' in t or 'recharge' in t or 'full talktime' in t:
            return '充值/话费优惠促销'
        if 'bhk' in t or 'flat' in t or 'plot' in t or 'apartment' in t:
            return '房产广告'
        if 'snapdeal' in t or 'easemytrip' in t:
            return '电商/旅游促销'
        if 'discount' in t or '% off' in t or '% discount' in t:
            return '折扣促销广告'
        if 'course' in t or 'admission' in t or 'training' in t:
            return '教育/课程招生广告'
        if 'hiring' in t or 'walk' in t or 'interview' in t:
            return '招聘广告'
        if 'loan' in t or 'emi' in t or 'insurance' in t:
            return '贷款/保险广告'
        if 'health' in t or 'treatment' in t or 'doctor' in t:
            return '医疗/健康服务广告'
        if 'holiday' in t or 'trip' in t or 'travel' in t:
            return '旅游/度假套餐广告'
        if 'food' in t or 'restaurant' in t or 'pizza' in t:
            return '餐饮/食品促销'
        if 'movie' in t or 'music' in t or 'game' in t:
            return '娱乐/内容服务广告'
        if 'data card' in t or '3g' in t or 'internet' in t:
            return '数据卡/网络服务广告'
        if 'caller tune' in t or 'ringtone' in t:
            return '彩铃/音乐服务广告'
        if 'offer' in t or 'deal' in t or 'sale' in t:
            return '促销/优惠活动广告'
        if 'free' in t or 'gift' in t:
            return '免费/赠品促销'
        if 'book' in t or 'buy' in t or 'shop' in t:
            return '购物/预订广告'
        if 'call now' in t or 'sms now' in t:
            return '即时行动促销广告'
        if 'limited' in t or 'hurry' in t or 'rush' in t:
            return '限时促销广告'
        if 'new' in t or 'latest' in t:
            return '新品/新款广告'
        if 'collection' in t or 'fashion' in t:
            return '时尚/服装广告'
        if 'property' in t or 'realty' in t or 'developer' in t:
            return '房产/开发商广告'
        if 'service' in t or 'repair' in t:
            return '维修服务广告'
        if 'bank' in t or 'credit card' in t:
            return '银行/信用卡广告'
        if 'contest' in t or 'competition' in t:
            return '竞赛/活动广告'
        if 'win' in t and ('mobile' in t or 'phone' in t or 'laptop' in t or 'bike' in t or 'car' in t or 'trip' in t or 'cash' in t or 'gold' in t or 'silver' in t or 'watch' in t or 'voucher' in t):
            return '有奖活动促销'
        if 'sms' in t and ('win' in t or 'prize' in t):
            return '短信抽奖促销'
        return '商业促销广告'
    else:
        return '内容不确定，需人工审核'

results = []
for r in records:
    rid = r['id']
    if rid in special_cases:
        label = special_cases[rid]
    else:
        label = classify(r['text'])
    reason = get_reason(r['text'], label)
    results.append({'id': rid, 'label': label, 'reason': reason})

# Output as JSON
output = json.dumps(results, ensure_ascii=False, indent=2)
with open(r'C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier\training\data\interim\annotation\result_1000_1699.json', 'w', encoding='utf-8') as f:
    f.write(output)

print(f"Total: {len(results)} records")
from collections import Counter
counts = Counter(r['label'] for r in results)
print("Counts:", dict(counts))
print("Output saved to result_1000_1699.json")
