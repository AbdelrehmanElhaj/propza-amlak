#!/bin/bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB="${ODOO_DB:-demodb}"
COMPOSE="$(bash "$SCRIPT_DIR/.compose")"

cd "$SCRIPT_DIR"

echo "=========================================="
echo "  تحميل البيانات التجريبية ×10 ← $DB"
echo "  Loading 10x Demo Data → $DB"
echo "=========================================="
echo ""

# ── Guard ──────────────────────────────────────────────────────────────────
if ! docker ps --format '{{.Names}}' | grep -q "^odoo17$"; then
    echo "ERROR: الحاويات غير مشغّلة. Odoo containers are not running."
    exit 1
fi

DB_EXISTS=$(docker exec odoo17-db psql -U odoo17 -d postgres -lqt 2>/dev/null \
    | cut -d'|' -f1 | tr -d ' ' | grep -x "$DB" || true)
if [ "$DB_EXISTS" != "$DB" ]; then
    echo "ERROR: قاعدة البيانات '$DB' غير موجودة. Database not found. Run ./create-demodb.sh first."
    exit 1
fi

echo "جارٍ تحميل البيانات ×10... (Seeding 10x data — 10-15 minutes)"
echo ""

$COMPOSE run --rm -T web odoo shell -d "$DB" << 'PYEOF'
import datetime
import random
import re

today = datetime.date.today()
ago   = lambda d: today - datetime.timedelta(days=d)
ahead = lambda d: today + datetime.timedelta(days=d)
dt    = lambda d, h=9: datetime.datetime.combine(d, datetime.time(h, 0))

# ══════════════════════════════════════════════════════════════════════════
# 0 — Helpers
# ══════════════════════════════════════════════════════════════════════════
SAR     = env['res.currency'].with_context(active_test=False).search([('name','=','SAR')], limit=1)
company = env['res.company'].search([], limit=1)
SA      = env['res.country'].search([('code','=','SA')], limit=1)

def region(code):
    return env['sa.region'].search([('code','=',code)], limit=1)
def city_sa(name):
    return env['sa.city'].search([('name','ilike',name)], limit=1)

r_riyadh = region('RUH') or env['sa.region'].search([], limit=1)
r_jeddah = region('MKH') or r_riyadh
r_dammam = region('EAS') or r_riyadh

c_riyadh = city_sa('الرياض') or env['sa.city'].search([], limit=1)
c_jeddah = city_sa('جدة')    or c_riyadh
c_dammam = city_sa('الدمام') or c_riyadh

# ══════════════════════════════════════════════════════════════════════════
# 0b — ملف الوساطة وبيانات إيجار
# ══════════════════════════════════════════════════════════════════════════
print("إعداد ملف الوساطة... (Setting up brokerage profile...)")

params = env['ir.config_parameter'].sudo()
params.set_param('ejar.api.key.company_%d' % company.id, 'PLACEHOLDER_API_KEY')
params.set_param('ejar.api.secret.company_%d' % company.id, 'PLACEHOLDER_API_SECRET')
params.set_param('ejar.api.environment.company_%d' % company.id, 'uat')

ejar_profile = env['ejar.brokerage.profile'].search([('company_id', '=', company.id)], limit=1)
if not ejar_profile:
    ejar_profile = env['ejar.brokerage.profile'].create({
        'company_id':             company.id,
        'office_name_ar':         'شركة بروبزا للوساطة العقارية',
        'office_name_en':         'Propza Real Estate Brokerage',
        'cr_number':              '1000000001',
        'unified_number':         '1000000001',
        'license_number':         'FB-LICENSE-001',
        'license_expiry':         str(ahead(365)),
        'vat_number':             '300000000000001',
        'national_address_code':  'RIYD0001',
        'building_number':        '1234',
        'street_ar':              'شارع الملك عبدالعزيز',
        'district_ar':            'حي العليا',
        'sa_region_id':           r_riyadh.id,
        'sa_city_id':             c_riyadh.id,
        'postal_code':            '12211',
        'is_verified':            False,
    })

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 1 — ملاك العقارات ×10 (40 ملاك)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء الملاك... (Creating 40 owners...)")

OWNER_BATCHES = [
    # batch 1 (original)
    [
        {'name':'محمد بن عبدالله القحطاني','company_type':'person','sa_national_id':'1023456789','sa_iban':'SA0380000000608010167519','phone':'+966501234001','email':'m.qahtani@propza-demo.sa','street':'شارع الإمام سعود','city':'الرياض'},
        {'name':'فاطمة بنت سعد الزهراني','company_type':'person','sa_national_id':'1056789012','sa_iban':'SA4420000001234567891234','phone':'+966502234002','email':'f.zahrani@propza-demo.sa','street':'شارع التحلية','city':'جدة'},
        {'name':'سالم بن أحمد العتيبي','company_type':'person','sa_national_id':'1078901234','sa_iban':'SA6220000003456789012345','phone':'+966503234003','email':'s.otaibi@propza-demo.sa','city':'الدمام'},
        {'name':'شركة الواحة للتطوير العقاري','company_type':'company','sa_cr_number':'1010345678','sa_iban':'SA1020000005678901234567','phone':'+966114001400','email':'info@alwaha-re.sa','street':'طريق الملك فهد','city':'الرياض','website':'https://alwaha-re.sa'},
    ],
    # batch 2
    [
        {'name':'عبدالعزيز بن سلطان الشمري','company_type':'person','sa_national_id':'1023456891','sa_iban':'SA0380000000608010167520','phone':'+966501234011','email':'a.shamari@propza-demo.sa','street':'شارع الأمير محمد','city':'الرياض'},
        {'name':'هنوف بنت خالد الرشيد','company_type':'person','sa_national_id':'1056789123','sa_iban':'SA4420000001234567891235','phone':'+966502234012','email':'h.rashid@propza-demo.sa','street':'شارع الأمين','city':'جدة'},
        {'name':'ناصر بن علي المطيري','company_type':'person','sa_national_id':'1078901345','sa_iban':'SA6220000003456789012346','phone':'+966503234013','email':'n.mutairi@propza-demo.sa','city':'الدمام'},
        {'name':'شركة النخيل للاستثمار العقاري','company_type':'company','sa_cr_number':'1010345679','sa_iban':'SA1020000005678901234568','phone':'+966114001401','email':'info@nakheel-inv.sa','street':'طريق الملك عبدالله','city':'الرياض','website':'https://nakheel-inv.sa'},
    ],
    # batch 3
    [
        {'name':'تركي بن فهد الحربي','company_type':'person','sa_national_id':'1023456902','sa_iban':'SA0380000000608010167521','phone':'+966501234021','email':'t.harbi@propza-demo.sa','street':'شارع الظهران','city':'الرياض'},
        {'name':'منيرة بنت عمر السبيعي','company_type':'person','sa_national_id':'1056789234','sa_iban':'SA4420000001234567891236','phone':'+966502234022','email':'m.subaie@propza-demo.sa','street':'شارع الفلاح','city':'جدة'},
        {'name':'وليد بن محمد الدوسري','company_type':'person','sa_national_id':'1078901456','sa_iban':'SA6220000003456789012347','phone':'+966503234023','email':'w.dosari@propza-demo.sa','city':'الدمام'},
        {'name':'شركة المدينة للتطوير','company_type':'company','sa_cr_number':'1010345680','sa_iban':'SA1020000005678901234569','phone':'+966114001402','email':'info@madina-dev.sa','street':'شارع الحزام','city':'الرياض'},
    ],
    # batch 4
    [
        {'name':'بندر بن سعود الغامدي','company_type':'person','sa_national_id':'1023456913','sa_iban':'SA0380000000608010167522','phone':'+966501234031','email':'b.ghamdi@propza-demo.sa','street':'شارع النفل','city':'الرياض'},
        {'name':'دلال بنت إبراهيم العمري','company_type':'person','sa_national_id':'1056789345','sa_iban':'SA4420000001234567891237','phone':'+966502234032','email':'d.omari@propza-demo.sa','street':'شارع المروة','city':'جدة'},
        {'name':'فراس بن عبدالله الشهري','company_type':'person','sa_national_id':'1078901567','sa_iban':'SA6220000003456789012348','phone':'+966503234033','email':'f.shehri@propza-demo.sa','city':'الدمام'},
        {'name':'شركة الأفق العقارية','company_type':'company','sa_cr_number':'1010345681','sa_iban':'SA1020000005678901234570','phone':'+966114001403','email':'info@ofok-re.sa','street':'طريق العروبة','city':'الرياض'},
    ],
    # batch 5
    [
        {'name':'راشد بن ناصر القرني','company_type':'person','sa_national_id':'1023456924','sa_iban':'SA0380000000608010167523','phone':'+966501234041','email':'r.qarni@propza-demo.sa','street':'شارع البطحاء','city':'الرياض'},
        {'name':'نوف بنت حمد العنزي','company_type':'person','sa_national_id':'1056789456','sa_iban':'SA4420000001234567891238','phone':'+966502234042','email':'n.anazi@propza-demo.sa','street':'شارع الكورنيش','city':'جدة'},
        {'name':'خلف بن مساعد الرشيدي','company_type':'person','sa_national_id':'1078901678','sa_iban':'SA6220000003456789012349','phone':'+966503234043','email':'k.rashidi@propza-demo.sa','city':'الدمام'},
        {'name':'شركة البناء الذهبي','company_type':'company','sa_cr_number':'1010345682','sa_iban':'SA1020000005678901234571','phone':'+966114001404','email':'info@golden-build.sa','street':'شارع الرياض','city':'الرياض'},
    ],
    # batch 6
    [
        {'name':'سطام بن فيصل الوهيبي','company_type':'person','sa_national_id':'1023456935','sa_iban':'SA0380000000608010167524','phone':'+966501234051','email':'s.wahaibi@propza-demo.sa','street':'شارع التخصصي','city':'الرياض'},
        {'name':'غادة بنت سليمان الزياني','company_type':'person','sa_national_id':'1056789567','sa_iban':'SA4420000001234567891239','phone':'+966502234052','email':'g.zayani@propza-demo.sa','street':'شارع الأندلس','city':'جدة'},
        {'name':'مشعل بن عبدالرحمن البلوي','company_type':'person','sa_national_id':'1078901789','sa_iban':'SA6220000003456789012350','phone':'+966503234053','email':'m.balawi@propza-demo.sa','city':'الدمام'},
        {'name':'شركة الرافدين العقارية','company_type':'company','sa_cr_number':'1010345683','sa_iban':'SA1020000005678901234572','phone':'+966114001405','email':'info@rafidain-re.sa','street':'طريق الدائري','city':'الرياض'},
    ],
    # batch 7
    [
        {'name':'عوض بن محمد السلمي','company_type':'person','sa_national_id':'1023456946','sa_iban':'SA0380000000608010167525','phone':'+966501234061','email':'a.salami@propza-demo.sa','street':'شارع القادسية','city':'الرياض'},
        {'name':'بسمة بنت علي الحمدان','company_type':'person','sa_national_id':'1056789678','sa_iban':'SA4420000001234567891240','phone':'+966502234062','email':'b.hamdan@propza-demo.sa','street':'شارع حراء','city':'جدة'},
        {'name':'ذياب بن أحمد الرويلي','company_type':'person','sa_national_id':'1078901890','sa_iban':'SA6220000003456789012351','phone':'+966503234063','email':'d.ruwaili@propza-demo.sa','city':'الدمام'},
        {'name':'شركة الشرق للتطوير','company_type':'company','sa_cr_number':'1010345684','sa_iban':'SA1020000005678901234573','phone':'+966114001406','email':'info@east-dev.sa','street':'شارع السلام','city':'الرياض'},
    ],
    # batch 8
    [
        {'name':'حمدان بن سعيد الزهراني','company_type':'person','sa_national_id':'1023456957','sa_iban':'SA0380000000608010167526','phone':'+966501234071','email':'h.zahrani2@propza-demo.sa','street':'شارع التعاون','city':'الرياض'},
        {'name':'لجين بنت حسن الغامدي','company_type':'person','sa_national_id':'1056789789','sa_iban':'SA4420000001234567891241','phone':'+966502234072','email':'l.ghamdi@propza-demo.sa','street':'شارع العروبة','city':'جدة'},
        {'name':'سعود بن طلال العجمي','company_type':'person','sa_national_id':'1078901901','sa_iban':'SA6220000003456789012352','phone':'+966503234073','email':'s.ajami@propza-demo.sa','city':'الدمام'},
        {'name':'شركة القمة العقارية','company_type':'company','sa_cr_number':'1010345685','sa_iban':'SA1020000005678901234574','phone':'+966114001407','email':'info@qimma-re.sa','street':'طريق الملك سلمان','city':'الرياض'},
    ],
    # batch 9
    [
        {'name':'لطيف بن عبدالله المقرن','company_type':'person','sa_national_id':'1023456968','sa_iban':'SA0380000000608010167527','phone':'+966501234081','email':'l.muqrin@propza-demo.sa','street':'شارع الأخضر','city':'الرياض'},
        {'name':'نجلاء بنت محمد اليحيى','company_type':'person','sa_national_id':'1056789890','sa_iban':'SA4420000001234567891242','phone':'+966502234082','email':'n.yahya@propza-demo.sa','street':'شارع الحمراء','city':'جدة'},
        {'name':'زياد بن يوسف الجهني','company_type':'person','sa_national_id':'1078902012','sa_iban':'SA6220000003456789012353','phone':'+966503234083','email':'z.juhani@propza-demo.sa','city':'الدمام'},
        {'name':'شركة الوسط للإسكان','company_type':'company','sa_cr_number':'1010345686','sa_iban':'SA1020000005678901234575','phone':'+966114001408','email':'info@wasat-housing.sa','street':'شارع التحلية','city':'الرياض'},
    ],
    # batch 10
    [
        {'name':'مبارك بن راشد الهاجري','company_type':'person','sa_national_id':'1023456979','sa_iban':'SA0380000000608010167528','phone':'+966501234091','email':'m.hajri@propza-demo.sa','street':'شارع المعذر','city':'الرياض'},
        {'name':'شيماء بنت عبدالعزيز المالكي','company_type':'person','sa_national_id':'1056789901','sa_iban':'SA4420000001234567891243','phone':'+966502234092','email':'sh.maliki@propza-demo.sa','street':'شارع النزهة','city':'جدة'},
        {'name':'خالد بن صالح الرشيدي','company_type':'person','sa_national_id':'1078902123','sa_iban':'SA6220000003456789012354','phone':'+966503234093','email':'kh.rashidi@propza-demo.sa','city':'الدمام'},
        {'name':'شركة الدرة للتطوير العقاري','company_type':'company','sa_cr_number':'1010345687','sa_iban':'SA1020000005678901234576','phone':'+966114001409','email':'info@durra-dev.sa','street':'طريق الملك فيصل','city':'الرياض'},
    ],
]

all_owners = []
for batch_idx, batch in enumerate(OWNER_BATCHES):
    batch_owners = []
    for o in batch:
        vals = {
            'company_type':      o['company_type'],
            'is_property_owner': True,
            'phone':             o['phone'],
            'email':             o['email'],
            'city':              o.get('city','الرياض'),
            'country_id':        SA.id,
            'name':              o['name'],
        }
        if 'sa_national_id' in o: vals['sa_national_id'] = o['sa_national_id']
        if 'sa_iban'        in o: vals['sa_iban']        = o['sa_iban']
        if 'sa_cr_number'   in o: vals['sa_cr_number']   = o['sa_cr_number']
        if 'street'         in o: vals['street']         = o['street']
        if 'website'        in o: vals['website']        = o['website']
        if o['company_type'] == 'person':
            vals['sa_id_type'] = 'national_id'
        batch_owners.append(env['res.partner'].create(vals))
    all_owners.append(batch_owners)
    print(f"  ✓ ملاك الدفعة {batch_idx+1} (Owners batch {batch_idx+1})")

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 2 — المستأجرون ×10 (100 مستأجر)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء المستأجرين... (Creating 100 tenants...)")

TENANT_DATA = [
    # name, id_type, national_id, phone_suffix, email_prefix, expiry_days
    ('خالد بن عبدالله الراشدي',  'national_id', '1098765432', '3100001', 'k.rashidi',  None),
    ('عمر محمد الفاروق',          'national_id', '1034512678', '3100002', 'o.farouq',   None),
    ('نورة سعد الحمدان',          'national_id', '1067891234', '3100003', 'n.hamdan',   None),
    ('عائشة أحمد مالك',           'iqama',       '2123456789', '3100004', 'a.malik',    180),
    ('أحمد يوسف العمري',          'national_id', '1055443322', '3100005', 'a.omari',    None),
    ('سارة عبدالرحمن الدوسري',    'national_id', '1066778899', '3100006', 's.dosari',   None),
    ('محمد علي الشهري',           'national_id', '1077889900', '3100007', 'm.shehri',   None),
    ('ريم عبدالعزيز القرني',      'national_id', '1088990011', '3100008', 'r.qarni',    None),
    ('فيصل محمد الغامدي',         'national_id', '1099887766', '3100009', 'f.ghamdi',   None),
    ('لمى عبدالله الزهراني',      'national_id', '1044332211', '3100010', 'l.zahrani',  None),
]

# suffixes to generate 10 batches
TENANT_SUFFIXES = [
    ('', ''),
    ('٢', 'b2'),
    ('٣', 'b3'),
    ('٤', 'b4'),
    ('٥', 'b5'),
    ('٦', 'b6'),
    ('٧', 'b7'),
    ('٨', 'b8'),
    ('٩', 'b9'),
    ('١٠', 'b10'),
]

# national ID base offsets per batch (shift last 3 digits)
ID_SHIFTS = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900]

all_tenants = []  # list of 10 batches, each with 10 tenants
for batch_idx, (name_sfx, email_sfx) in enumerate(TENANT_SUFFIXES):
    id_shift = ID_SHIFTS[batch_idx]
    batch_tenants = []
    for t in TENANT_DATA:
        tname, id_type, nat_id, ph_sfx, em_pfx, exp = t
        # make unique IDs by incrementing
        base_id = int(nat_id)
        new_id  = str(base_id + id_shift).zfill(len(nat_id))
        suffix_str = f'-{email_sfx}' if email_sfx else ''
        vals = {
            'name':           tname + (f' {name_sfx}' if name_sfx else ''),
            'company_type':   'person',
            'is_tenant':      True,
            'sa_id_type':     id_type,
            'sa_national_id': new_id,
            'phone':          f'+9665{ph_sfx}{str(batch_idx).zfill(2)}',
            'email':          f'{em_pfx}{suffix_str}@propza-demo.sa',
            'country_id':     SA.id,
        }
        if exp:
            vals['sa_id_expiry'] = str(ahead(exp))
        batch_tenants.append(env['res.partner'].create(vals))
    all_tenants.append(batch_tenants)
    print(f"  ✓ مستأجرو الدفعة {batch_idx+1} (Tenants batch {batch_idx+1})")

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 3 — الوسطاء ×10 (30 وسيط)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء الوسطاء... (Creating 30 brokers...)")

BROKER_TEMPLATES = [
    {'name':'شركة الوافر للوساطة العقارية','company_type':'company','broker_license':'BRK-2024-00123','sa_cr_number':'4030234567','phone':'+966122345678','email':'info@alwafer-broker.sa','city':'الرياض'},
    {'name':'طارق بن محمد الغامدي',        'company_type':'person', 'broker_license':'BRK-2024-00456','sa_national_id':'1045678901','phone':'+966504200002','email':'t.ghamdi@broker.sa'},
    {'name':'هند بنت سليمان العمودي',      'company_type':'person', 'broker_license':'BRK-2024-00789','sa_national_id':'1099001122','phone':'+966504200003','email':'h.amodi@broker.sa'},
]

all_brokers = []
for batch_idx in range(10):
    sfx = '' if batch_idx == 0 else f'-{batch_idx+1}'
    batch_brokers = []
    for i, b in enumerate(BROKER_TEMPLATES):
        vals = {
            'name':           b['name'] + (f' {batch_idx+1}' if batch_idx > 0 else ''),
            'company_type':   b['company_type'],
            'is_broker':      True,
            'broker_license': b['broker_license'] + (f'{batch_idx}' if batch_idx > 0 else ''),
            'phone':          b['phone'][:-1] + str(batch_idx),
            'email':          b['email'].replace('@', f'{sfx}@'),
            'country_id':     SA.id,
        }
        if 'sa_cr_number'   in b: vals['sa_cr_number']   = str(int(b['sa_cr_number'])   + batch_idx)
        if 'sa_national_id' in b: vals['sa_national_id'] = str(int(b['sa_national_id']) + batch_idx * 100)
        if 'city'           in b: vals['city']           = b['city']
        if b['company_type'] == 'person': vals['sa_id_type'] = 'national_id'
        batch_brokers.append(env['res.partner'].create(vals))
    all_brokers.append(batch_brokers)

env.cr.commit()
print(f"  ✓ {len(all_brokers)*3} وسيط (brokers)")

# ══════════════════════════════════════════════════════════════════════════
# 4 — الفنيون ×10 (30 فني)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء الفنيين... (Creating 30 technicians...)")

plumbing_skill   = env['sa.maintenance.skill'].search([('code','=','PLM')], limit=1)
electrical_skill = env['sa.maintenance.skill'].search([('code','=','ELC')], limit=1)
ac_skill         = env['sa.maintenance.skill'].search([('code','=','ACA')], limit=1)
painting_skill   = env['sa.maintenance.skill'].search([('code','=','PNT')], limit=1)
carpentry_skill  = env['sa.maintenance.skill'].search([('code','=','CRP')], limit=1)

TECH_TEMPLATES = [
    {'name':'حسن البحار للسباكة والصرف الصحي',       'company_type':'company','sa_cr_number':'1010556677','sa_hourly_rate':80.0, 'sa_call_out_fee':50.0,'sa_response_hours':4,'skills':lambda: plumbing_skill.ids,               'phone':'+966112345601','email':'info@hassan-plumbing.sa',  'city':'الرياض'},
    {'name':'شركة أحمد للتقنية الكهربائية والتكييف',  'company_type':'company','sa_cr_number':'1010667788','sa_hourly_rate':100.0,'sa_call_out_fee':75.0,'sa_response_hours':2,'skills':lambda: (electrical_skill+ac_skill).ids,  'phone':'+966114502000','email':'support@ahmad-tech.sa',    'city':'الرياض'},
    {'name':'عبدالله الحربي للدهانات والأعمال الخشبية','company_type':'person', 'sa_national_id':'1033221100','sa_hourly_rate':65.0,'sa_call_out_fee':30.0,'sa_response_hours':6,'skills':lambda: (painting_skill+carpentry_skill).ids,'phone':'+966505400003','email':'a.harbi@handyman.sa'},
]

all_techs = []
for batch_idx in range(10):
    batch_techs = []
    for i, t in enumerate(TECH_TEMPLATES):
        vals = {
            'name':              t['name'] + (f' {batch_idx+1}' if batch_idx > 0 else ''),
            'company_type':      t['company_type'],
            'is_technician':     True,
            'sa_hourly_rate':    t['sa_hourly_rate'],
            'sa_call_out_fee':   t['sa_call_out_fee'],
            'sa_response_hours': t['sa_response_hours'],
            'sa_skill_ids':      [(6, 0, t['skills']())],
            'phone':             t['phone'][:-1] + str(batch_idx),
            'email':             t['email'].replace('@', f'{"-"+str(batch_idx) if batch_idx>0 else ""}@'),
            'country_id':        SA.id,
        }
        if 'sa_cr_number'   in t: vals['sa_cr_number']   = str(int(t['sa_cr_number'])   + batch_idx)
        if 'sa_national_id' in t: vals['sa_national_id'] = str(int(t['sa_national_id']) + batch_idx * 100)
        if 'city'           in t: vals['city']           = t['city']
        if t['company_type'] == 'person': vals['sa_id_type'] = 'national_id'
        batch_techs.append(env['res.partner'].create(vals))
    all_techs.append(batch_techs)

env.cr.commit()
print(f"  ✓ {len(all_techs)*3} فني (technicians)")

# ══════════════════════════════════════════════════════════════════════════
# 5 — العقارات ×10 (120 عقار)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء العقارات... (Creating 120 properties...)")

def make_prop(vals):
    return env['property.property'].create(vals)

PROP_TEMPLATES = [
    # Villas
    {'name':'فيلا الروضة','flat_name':'حي الروضة – شارع الإمام سعود','description':'فيلا فاخرة من طابقين بحديقة خاصة ومسبح.','property_type':'residential','sa_property_subtype':'villa','rent_amount':80000.0,'deposit_amount':80000.0,'owner_idx':0,'sa_district':'حي الروضة','sa_street':'شارع الإمام سعود','sa_building_no':'12','sa_postal_code':'12241','sa_area_sqm':450.0,'sa_rooms':5,'sa_bathrooms':4,'sa_parking':2,'sa_pool':True,'sa_garden':True,'sa_furnished':'unfurnished','sa_condition':'excellent','sa_year_built':2018,'region':'r','city':'c_riyadh'},
    {'name':'فيلا النزهة','flat_name':'حي النزهة – جدة','description':'فيلا واسعة مع إطلالة على الحديقة.','property_type':'residential','sa_property_subtype':'villa','rent_amount':95000.0,'deposit_amount':95000.0,'owner_idx':1,'sa_district':'حي النزهة','sa_street':'شارع الأمير سلطان','sa_building_no':'8','sa_area_sqm':520.0,'sa_rooms':6,'sa_bathrooms':5,'sa_parking':3,'sa_pool':True,'sa_furnished':'semi','sa_condition':'excellent','sa_year_built':2020,'region':'j','city':'c_jeddah'},
    {'name':'فيلا النرجس','flat_name':'حي النرجس – الرياض','description':'فيلا حديثة في حي النرجس الهادئ.','property_type':'residential','sa_property_subtype':'villa','rent_amount':110000.0,'deposit_amount':110000.0,'owner_idx':3,'sa_district':'حي النرجس','sa_building_no':'3','sa_area_sqm':600.0,'sa_rooms':6,'sa_bathrooms':5,'sa_parking':3,'sa_pool':True,'sa_garden':True,'sa_furnished':'fully','sa_condition':'excellent','sa_year_built':2022,'region':'r','city':'c_riyadh'},
    # Apartments - Riyadh
    {'name':'شقة العليا','flat_name':'برج العليا، الدور ٣ – حي العليا','description':'شقة ثلاث غرف في برج راقٍ بحي العليا.','property_type':'residential','sa_property_subtype':'apartment','rent_amount':45000.0,'deposit_amount':22500.0,'owner_idx':0,'sa_district':'حي العليا','sa_street':'طريق الملك فهد','sa_floor_number':3,'sa_total_floors':10,'sa_area_sqm':140.0,'sa_rooms':3,'sa_bathrooms':2,'sa_elevator':True,'sa_furnished':'semi','sa_condition':'good','sa_year_built':2015,'region':'r','city':'c_riyadh'},
    {'name':'شقة الملقا','flat_name':'برج الملقا، الدور ٧ – حي الملقا','description':'شقة فسيحة في حي الملقا.','property_type':'residential','sa_property_subtype':'apartment','rent_amount':48000.0,'deposit_amount':24000.0,'owner_idx':0,'sa_district':'حي الملقا','sa_floor_number':7,'sa_total_floors':15,'sa_area_sqm':160.0,'sa_rooms':3,'sa_bathrooms':2,'sa_elevator':True,'sa_furnished':'unfurnished','sa_condition':'good','region':'r','city':'c_riyadh'},
    # Apartments - Jeddah & Dammam
    {'name':'شقة الحمراء','flat_name':'عمارة الحمراء، الدور ٢ – جدة','description':'شقة مطلة على الشارع في حي الحمراء الراقي.','property_type':'residential','sa_property_subtype':'apartment','rent_amount':42000.0,'deposit_amount':21000.0,'owner_idx':1,'sa_district':'حي الحمراء','sa_floor_number':2,'sa_area_sqm':130.0,'sa_rooms':3,'sa_bathrooms':2,'sa_furnished':'semi','sa_condition':'good','region':'j','city':'c_jeddah'},
    {'name':'شقة المرجان','flat_name':'برج المرجان، الدور ٤ – الدمام','description':'شقة حديثة في حي المرجان بالدمام.','property_type':'residential','sa_property_subtype':'apartment','rent_amount':38000.0,'deposit_amount':19000.0,'owner_idx':2,'sa_district':'حي المرجان','sa_floor_number':4,'sa_area_sqm':120.0,'sa_rooms':3,'sa_bathrooms':2,'sa_elevator':True,'sa_furnished':'unfurnished','sa_condition':'good','sa_year_built':2019,'region':'d','city':'c_dammam'},
    {'name':'شقة الدانة','flat_name':'عمارة الدانة، الدور ١ – الدمام','description':'شقة بسعر مناسب في حي الدانة.','property_type':'residential','sa_property_subtype':'apartment','rent_amount':35000.0,'deposit_amount':17500.0,'owner_idx':2,'sa_district':'حي الدانة','sa_floor_number':1,'sa_area_sqm':110.0,'sa_rooms':2,'sa_bathrooms':2,'sa_furnished':'unfurnished','sa_condition':'good','region':'d','city':'c_dammam'},
    # Offices
    {'name':'مكتب بيزنس باي','flat_name':'برج بيزنس باي، الدور ٢٠ – حي العليا','description':'مكتب تنفيذي بإطلالة بانورامية.','property_type':'commercial','sa_property_subtype':'office','rent_amount':120000.0,'deposit_amount':60000.0,'owner_idx':3,'sa_district':'حي العليا','sa_street':'طريق الملك فهد','sa_floor_number':20,'sa_total_floors':30,'sa_area_sqm':280.0,'sa_elevator':True,'sa_furnished':'fully','sa_condition':'excellent','sa_year_built':2022,'region':'r','city':'c_riyadh'},
    {'name':'مكتب طريق الملك فهد','flat_name':'مجمع الملك فهد التجاري، الدور ٥','description':'مكتب نصف مجهز في موقع استراتيجي.','property_type':'commercial','sa_property_subtype':'office','rent_amount':85000.0,'deposit_amount':42500.0,'owner_idx':3,'sa_district':'حي الورود','sa_floor_number':5,'sa_area_sqm':200.0,'sa_elevator':True,'sa_furnished':'semi','sa_condition':'good','region':'r','city':'c_riyadh'},
    # Shop & Warehouse
    {'name':'محل الشميسي التجاري','flat_name':'مجمع الشميسي التجاري','description':'محل تجاري يُصلح للبيع بالتجزئة.','property_type':'commercial','sa_property_subtype':'shop','rent_amount':55000.0,'deposit_amount':55000.0,'owner_idx':2,'sa_district':'حي الشميسي','sa_area_sqm':90.0,'sa_condition':'good','sa_year_built':2014,'region':'r','city':'c_riyadh'},
    {'name':'مستودع الرياض الصناعي','flat_name':'المدينة الصناعية الثانية','description':'مستودع واسع مناسب للتخزين والتوزيع.','property_type':'commercial','sa_property_subtype':'warehouse','rent_amount':60000.0,'deposit_amount':60000.0,'owner_idx':3,'sa_district':'المدينة الصناعية الثانية','sa_area_sqm':800.0,'sa_condition':'good','sa_year_built':2016,'region':'r','city':'c_riyadh'},
]

REGION_MAP  = {'r': r_riyadh, 'j': r_jeddah, 'd': r_dammam}
CITY_MAP    = {'c_riyadh': c_riyadh, 'c_jeddah': c_jeddah, 'c_dammam': c_dammam}

all_props = []  # 10 batches × 12 props
for batch_idx, owner_batch in enumerate(all_owners):
    batch_props = []
    for p in PROP_TEMPLATES:
        owner = owner_batch[p['owner_idx']]
        region_rec = REGION_MAP[p['region']]
        city_rec   = CITY_MAP[p['city']]
        unit_sfx   = f' – {batch_idx+1}' if batch_idx > 0 else ''
        vals = {
            'name':             p['name'] + unit_sfx,
            'flat_name':        p.get('flat_name','') + unit_sfx,
            'description':      p.get('description',''),
            'property_type':    p['property_type'],
            'sa_property_subtype': p['sa_property_subtype'],
            'owner_partner_id': owner.id,
            'rent_amount':      p['rent_amount'],
            'deposit_amount':   p['deposit_amount'],
            'currency_id':      SAR.id,
            'sa_region_id':     region_rec.id,
            'sa_city_id':       city_rec.id,
            'sa_area_sqm':      p.get('sa_area_sqm', 100.0),
            'sa_condition':     p.get('sa_condition','good'),
            'sa_furnished':     p.get('sa_furnished','unfurnished'),
        }
        for fld in ['sa_district','sa_street','sa_building_no','sa_postal_code','sa_rooms',
                    'sa_bathrooms','sa_parking','sa_floor_number','sa_total_floors',
                    'sa_year_built','sa_deed_number','sa_elevator','sa_pool','sa_garden']:
            if fld in p:
                vals[fld] = p[fld]
        batch_props.append(make_prop(vals))
    all_props.append(batch_props)
    print(f"  ✓ عقارات الدفعة {batch_idx+1} (Properties batch {batch_idx+1})")
    env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 6 — عقود الإيجار ×10 (90 عقد)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء عقود الإيجار... (Creating 90 tenancies...)")

def tenancy(vals, confirm=True, start=True):
    t = env['property.tenancy'].create(vals)
    if confirm: t.action_confirm()
    if start:   t.action_start()
    return t

# Template: (prop_idx, tenant_idx, start_ago, end_ahead, duration, interval,
#            rent, deposit, method, contract_type, schedule, ejar_sched, broker_idx,
#            confirm, start)
TENANCY_TEMPLATES = [
    (0, 0, 180, 185, 12,'months', 80000.0, 80000.0, 'sadad',         'residential','quarterly',  'quarterly',  0, True,  True),
    (3, 1, 90,  275, 12,'months', 45000.0, 22500.0, 'bank_transfer',  'residential','quarterly',  'quarterly',  1, True,  True),
    (4, 2, 120, 245, 12,'months', 48000.0, 24000.0, 'mada',           'residential','monthly',    'monthly',    -1,True,  True),
    (5, 3, 337, 28,  12,'months', 42000.0, 21000.0, 'bank_transfer',  'residential','annual',     'annual',     2, True,  True),
    (8, 4, 365, 0,   12,'months',120000.0, 60000.0, 'bank_transfer',  'commercial', 'quarterly',  'quarterly',  0, True,  True),
    (6, 5, 60,  305, 12,'months', 38000.0, 19000.0, 'sadad',          'residential','monthly',    'monthly',    -1,True,  True),
    (10,6, 240, 125, 12,'months', 55000.0, 55000.0, 'cheque',         'commercial', 'semi_annual','semi_annual',2, True,  True),
    (7, 7, -15, 380, 12,'months', 35000.0, 17500.0, 'bank_transfer',  'residential','quarterly',  'quarterly',  -1,True,  False),
    (2, 0, -45, 410, 12,'months',110000.0,110000.0, 'bank_transfer',  'residential','semi_annual','semi_annual',-1,False, False),
]

all_tenancies = []
for batch_idx in range(10):
    props   = all_props[batch_idx]
    tenants = all_tenants[batch_idx]
    brokers = all_brokers[batch_idx]
    batch_tenancies = []
    for tmpl in TENANCY_TEMPLATES:
        (pidx, tidx, s_ago, e_ahead, dur, intvl,
         rent, dep, method, ctype, sched, esched, bidx, do_confirm, do_start) = tmpl
        # handle negative ago (means ahead)
        start_date = ago(s_ago)   if s_ago  >= 0 else ahead(-s_ago)
        end_date   = ahead(e_ahead) if e_ahead >= 0 else ago(-e_ahead)
        # tenant national id
        tenant_obj = tenants[tidx]
        ten_nat_id = tenant_obj.sa_national_id or ''
        ten_id_type = tenant_obj.sa_id_type or 'national_id'
        vals = {
            'property_id':           props[pidx].id,
            'partner_id':            tenant_obj.id,
            'start_date':            str(start_date),
            'end_date':              str(end_date),
            'duration':              dur,
            'interval_type':         intvl,
            'rent_amount':           rent,
            'deposit_amount':        dep,
            'currency_id':           SAR.id,
            'payment_method':        method,
            'sa_contract_type':      ctype,
            'sa_payment_schedule':   sched,
            'ejar_payment_schedule': esched,
            'tenant_id_type':        ten_id_type,
            'tenant_national_id':    ten_nat_id,
            'sublease_allowed':      False,
        }
        if bidx >= 0:
            vals['sa_broker_id'] = brokers[bidx].id
        batch_tenancies.append(tenancy(vals, confirm=do_confirm, start=do_start))
    all_tenancies.append(batch_tenancies)
    print(f"  ✓ عقود الدفعة {batch_idx+1} (Tenancies batch {batch_idx+1})")
    env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 7 — دفعات الإيجار ×10
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء دفعات الإيجار... (Creating rent payments...)")

def pay(ten, due, amount, state='pending', paid_on=None, method=None,
        ptype='rent', label=''):
    v = {
        'tenancy_id':   ten.id,
        'due_date':     str(due),
        'amount':       amount,
        'payment_type': ptype,
        'state':        state,
        'period_label': label,
    }
    if paid_on:
        v['payment_date'] = str(paid_on)
        v['amount_paid']  = amount
    if method:
        v['payment_method'] = method
    return env['sa.rent.payment'].create(v)

def deposit_pay(ten, on, amount, method='bank_transfer'):
    pay(ten, on, amount, 'paid', on, method, 'deposit', 'وديعة تأمين')

for batch_idx, batch_tens in enumerate(all_tenancies):
    t1b,t2b,t3b,t4b,t5b,t6b,t7b,t8b,t9b = batch_tens

    # t1 — ربع سنوي
    deposit_pay(t1b, ago(180), 80000.0, 'sadad')
    pay(t1b, ago(180), 20000.0, 'paid', ago(178), 'sadad', label='الربع الأول')
    pay(t1b, ago(90),  20000.0, 'paid', ago(88),  'sadad', label='الربع الثاني')
    pay(t1b, today,    20000.0, 'pending',                  label='الربع الثالث')
    pay(t1b, ahead(90),20000.0, 'pending',                  label='الربع الرابع')

    # t2 — ربع سنوي
    deposit_pay(t2b, ago(90), 22500.0, 'bank_transfer')
    pay(t2b, ago(90),   11250.0, 'paid',    ago(88), 'bank_transfer', label='الربع الأول')
    pay(t2b, today,     11250.0, 'pending',                            label='الربع الثاني')
    pay(t2b, ahead(90), 11250.0, 'pending',                            label='الربع الثالث')
    pay(t2b, ahead(180),11250.0, 'pending',                            label='الربع الرابع')

    # t3 — شهري مع دفعة متأخرة
    deposit_pay(t3b, ago(120), 24000.0, 'mada')
    monthly = round(48000.0 / 12, 2)
    for due, st, pd, lbl in [
        (ago(120),'paid',   ago(118),'الشهر الأول'),
        (ago(90), 'paid',   ago(88), 'الشهر الثاني'),
        (ago(60), 'paid',   ago(58), 'الشهر الثالث'),
        (ago(30), 'overdue',None,    'الشهر الرابع'),
        (today,   'pending',None,    'الشهر الخامس'),
    ]:
        pay(t3b, due, monthly, st, pd, 'mada' if pd else None, label=lbl)

    # t4 — سنوي كامل
    deposit_pay(t4b, ago(337), 21000.0, 'bank_transfer')
    pay(t4b, ago(337), 42000.0, 'paid', ago(335), 'bank_transfer', label='الإيجار السنوي')

    # t5 — ربع سنوي ×4 مدفوع
    deposit_pay(t5b, ago(365), 60000.0, 'bank_transfer')
    for due, lbl in [(ago(365),'الربع الأول'),(ago(275),'الربع الثاني'),(ago(185),'الربع الثالث'),(ago(95),'الربع الرابع')]:
        pay(t5b, due, 30000.0, 'paid', due + datetime.timedelta(2), 'bank_transfer', label=lbl)

    # t6 — شهري
    deposit_pay(t6b, ago(60), 19000.0, 'sadad')
    monthly6 = round(38000.0 / 12, 2)
    for due, st, pd, lbl in [(ago(60),'paid',ago(58),'الشهر الأول'),(ago(30),'paid',ago(28),'الشهر الثاني'),(today,'pending',None,'الشهر الثالث')]:
        pay(t6b, due, monthly6, st, pd, 'sadad' if pd else None, label=lbl)

    # t7 — نصف سنوي
    deposit_pay(t7b, ago(240), 55000.0, 'cheque')
    pay(t7b, ago(240), 27500.0, 'paid', ago(238), 'cheque', label='النصف الأول')
    pay(t7b, ahead(250),27500.0, 'pending', label='النصف الثاني')

    # t8 — وديعة فقط
    deposit_pay(t8b, today, 17500.0, 'bank_transfer')

    env.cr.commit()

print(f"  ✓ دفعات الإيجار (Rent payments)")

# ══════════════════════════════════════════════════════════════════════════
# 8 — المعاينات ×10 (50 معاينة)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء المعاينات... (Creating 50 inspections...)")

def inspection(vals, complete=False, sign=False):
    ins = env['sa.property.inspection'].create(vals)
    if complete or sign: ins.action_complete()
    if sign:             ins.action_sign()
    return ins

for batch_idx in range(10):
    props = all_props[batch_idx]
    tens  = all_tenancies[batch_idx]

    inspection({'property_id':props[0].id,'tenancy_id':tens[0].id,'inspection_type':'move_in','inspection_date':str(ago(180)),'general_condition':'excellent','general_notes':'العقار في حالة ممتازة.','line_ids':[(0,0,{'room':'living_room','item':'أجهزة التكييف','condition':'good'}),(0,0,{'room':'kitchen','item':'خزائن المطبخ','condition':'good'}),(0,0,{'room':'bathroom','item':'تجهيزات السباكة','condition':'good'}),]},complete=True,sign=True)
    inspection({'property_id':props[5].id,'tenancy_id':tens[3].id,'inspection_type':'move_in','inspection_date':str(ago(337)),'general_condition':'good','general_notes':'الشقة في حالة جيدة.','line_ids':[(0,0,{'room':'living_room','item':'الجدران','condition':'minor_wear','damage_cost':800.0}),(0,0,{'room':'kitchen','item':'الأجهزة','condition':'good'}),]},complete=True,sign=True)
    inspection({'property_id':props[5].id,'tenancy_id':tens[3].id,'inspection_type':'interim','inspection_date':str(today),'general_condition':'fair','general_notes':'معاينة مرحلية قبيل انتهاء العقد.','line_ids':[(0,0,{'room':'living_room','item':'الجدران','condition':'damaged','damage_cost':1500.0}),(0,0,{'room':'bathroom','item':'البلاط','condition':'minor_wear','damage_cost':400.0}),]})
    inspection({'property_id':props[3].id,'tenancy_id':tens[1].id,'inspection_type':'move_in','inspection_date':str(ago(90)),'general_condition':'good','general_notes':'الشقة نظيفة وجاهزة.','line_ids':[(0,0,{'room':'kitchen','item':'المطبخ والأجهزة','condition':'good','notes':'جهاز الغسيل جديد'}),(0,0,{'room':'bathroom','item':'الحمام الرئيسي','condition':'good'}),]},complete=True)
    inspection({'property_id':props[8].id,'tenancy_id':tens[4].id,'inspection_type':'move_in','inspection_date':str(ago(365)),'general_condition':'excellent','general_notes':'المكتب مجهز بالكامل.','line_ids':[(0,0,{'room':'other','item':'أجهزة التكييف','condition':'good'}),(0,0,{'room':'other','item':'شبكة الإنترنت','condition':'good','notes':'١ جيجابت'}),]},complete=True,sign=True)

    env.cr.commit()

print(f"  ✓ المعاينات (Inspections)")

# ══════════════════════════════════════════════════════════════════════════
# 9 — طلبات الصيانة وأوامر العمل ×10
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء طلبات الصيانة... (Creating maintenance requests...)")

for batch_idx in range(10):
    props = all_props[batch_idx]
    tens  = all_tenancies[batch_idx]
    techs = all_techs[batch_idx]
    tech1b, tech2b, tech3b = techs

    req1 = env['sa.maintenance.request'].create({'property_id':props[0].id,'tenancy_id':tens[0].id,'description':'عطل في وحدة التكييف المركزي.','request_date':str(ago(5)),'category':'ac','priority':'2','supplier_partner_id':tech2b.id,'scheduled_date':str(dt(ahead(1),10)),'estimated_duration':3.0,'labor_cost':300.0,'materials_cost':150.0,'cost_bearer':'owner'})
    req1.action_approve(); req1.action_schedule(); req1.action_start()

    req2 = env['sa.maintenance.request'].create({'property_id':props[3].id,'tenancy_id':tens[1].id,'description':'تسرب مياه أسفل حوض المطبخ.','request_date':str(ago(2)),'category':'plumbing','priority':'3','supplier_partner_id':tech1b.id,'scheduled_date':str(dt(today,9)),'estimated_duration':2.0,'labor_cost':200.0,'materials_cost':80.0,'cost_bearer':'owner'})
    req2.action_approve()

    req3 = env['sa.maintenance.request'].create({'property_id':props[8].id,'tenancy_id':tens[4].id,'description':'وميض في مصابيح السقف.','request_date':str(ago(7)),'category':'electrical','priority':'2','supplier_partner_id':tech2b.id,'scheduled_date':str(dt(ago(1),14)),'actual_duration':2.5,'labor_cost':350.0,'materials_cost':220.0,'cost_bearer':'tenant'})
    req3.action_approve(); req3.action_schedule(); req3.action_start(); req3.action_done()

    req4 = env['sa.maintenance.request'].create({'property_id':props[4].id,'tenancy_id':tens[2].id,'description':'قفل الباب الأمامي معطل.','request_date':str(today),'category':'carpentry','priority':'3','estimated_duration':1.0,'labor_cost':150.0,'materials_cost':200.0,'cost_bearer':'owner'})

    req5 = env['sa.maintenance.request'].create({'property_id':props[5].id,'tenancy_id':tens[3].id,'description':'إعادة طلاء جدران غرفة المعيشة.','request_date':str(ago(1)),'category':'painting','priority':'1','supplier_partner_id':tech3b.id,'scheduled_date':str(dt(ahead(7),8)),'estimated_duration':8.0,'labor_cost':600.0,'materials_cost':400.0,'cost_bearer':'tenant'})
    req5.action_approve()

    req6 = env['sa.maintenance.request'].create({'property_id':props[6].id,'tenancy_id':tens[5].id,'description':'تلف وتشقق في بلاط حمام غرفة النوم.','request_date':str(ago(1)),'category':'other','priority':'1','estimated_duration':4.0,'labor_cost':400.0,'materials_cost':500.0,'cost_bearer':'owner'})

    req7 = env['sa.maintenance.request'].create({'property_id':props[1].id,'description':'الخزان العلوي للمياه يصدر أصواتاً.','request_date':str(ago(3)),'category':'plumbing','priority':'2','supplier_partner_id':tech1b.id,'scheduled_date':str(dt(ahead(2),11)),'estimated_duration':3.0,'labor_cost':250.0,'materials_cost':300.0,'cost_bearer':'owner'})
    req7.action_approve(); req7.action_schedule()

    req8 = env['sa.maintenance.request'].create({'property_id':props[0].id,'tenancy_id':tens[0].id,'description':'الصيانة الدورية للحديقة والمسبح.','request_date':str(ago(14)),'category':'other','priority':'0','supplier_partner_id':tech3b.id,'scheduled_date':str(dt(ago(13),8)),'actual_duration':6.0,'labor_cost':400.0,'materials_cost':150.0,'cost_bearer':'owner'})
    req8.action_approve(); req8.action_schedule(); req8.action_start(); req8.action_done()

    # Work orders
    wo1 = env['sa.maintenance.work_order'].create({'request_id':req1.id,'technician_id':tech2b.id,'description':'فحص وحدات التكييف.','scheduled_date':str(dt(ahead(1),10)),'duration_planned':3.0,'labor_cost':300.0,'materials_cost':150.0})
    wo1.action_schedule()
    wo2 = env['sa.maintenance.work_order'].create({'request_id':req3.id,'technician_id':tech2b.id,'description':'استبدال المصابيح المعيبة.','scheduled_date':str(dt(ago(1),14)),'duration_planned':2.5,'duration_actual':2.5,'labor_cost':350.0,'materials_cost':220.0})
    wo2.action_schedule(); wo2.action_start(); wo2.action_done()
    wo3 = env['sa.maintenance.work_order'].create({'request_id':req7.id,'technician_id':tech1b.id,'description':'فحص خزان المياه.','scheduled_date':str(dt(ahead(2),11)),'duration_planned':3.0,'labor_cost':250.0,'materials_cost':300.0})
    wo3.action_schedule()
    wo4 = env['sa.maintenance.work_order'].create({'request_id':req8.id,'technician_id':tech3b.id,'description':'تنظيف المسبح وصيانة الحديقة.','scheduled_date':str(dt(ago(14),8)),'duration_planned':6.0,'duration_actual':6.0,'labor_cost':400.0,'materials_cost':150.0})
    wo4.action_schedule(); wo4.action_start(); wo4.action_done()

    env.cr.commit()

print(f"  ✓ الصيانة (Maintenance)")

# ══════════════════════════════════════════════════════════════════════════
# 10 — عقود الصيانة الدورية ×10 (20 عقد)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء عقود الصيانة... (Creating maintenance contracts...)")

for batch_idx in range(10):
    props = all_props[batch_idx]
    techs = all_techs[batch_idx]

    mc1 = env['sa.maintenance.contract'].create({'supplier_partner_id':techs[1].id,'property_ids':[(6,0,[props[0].id,props[8].id])],'category':'ac','frequency':'quarterly','start_date':str(ago(90)),'end_date':str(ahead(275)),'service_description':'صيانة دورية ربع سنوية لأجهزة التكييف.','estimated_cost_per_visit':750.0})
    mc1.action_activate()
    mc2 = env['sa.maintenance.contract'].create({'supplier_partner_id':techs[0].id,'property_ids':[(6,0,[props[3].id,props[4].id,props[6].id])],'category':'plumbing','frequency':'annual','start_date':str(ago(30)),'end_date':str(ahead(335)),'service_description':'فحص وصيانة سنوية لشبكات السباكة.','estimated_cost_per_visit':500.0})
    mc2.action_activate()

    env.cr.commit()

print(f"  ✓ عقود الصيانة (Maintenance contracts)")

# ══════════════════════════════════════════════════════════════════════════
# 11 — عمولات الوسطاء ×10 (40 عمولة)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء عمولات الوسطاء... (Creating broker commissions...)")

for batch_idx in range(10):
    brokers = all_brokers[batch_idx]
    tens    = all_tenancies[batch_idx]

    for broker_obj, tenancy_obj, notes, lines in [
        (brokers[0], tens[0], 'عمولة على تأجير الفيلا', [('عمولة توقيع العقد', ago(180), 4000.0)]),
        (brokers[1], tens[1], 'عمولة على تأجير شقة العليا', [('عمولة توقيع العقد', ago(90), 2250.0)]),
        (brokers[2], tens[3], 'عمولة على تأجير شقة الحمراء', [('عمولة توقيع العقد', ago(337), 2100.0)]),
        (brokers[0], tens[4], 'عمولة مكتب بيزنس باي', [('القسط الأول', ago(365), 3000.0),('القسط الثاني', ago(185), 3000.0)]),
    ]:
        comm = env['sa.broker.commission'].create({
            'broker_partner_id': broker_obj.id,
            'tenancy_id':        tenancy_obj.id,
            'commission_type':   'percentage',
            'commission_rate':   5.0,
            'payment_schedule':  'on_signup',
            'date_signed':       str(lines[0][1]),
            'notes':             notes,
            'line_ids': [(0,0,{'description':desc,'due_date':str(due),'amount':amt,'state':'paid'}) for desc, due, amt in lines],
        })
        comm.action_confirm()

    env.cr.commit()

print(f"  ✓ العمولات (Commissions)")

# ══════════════════════════════════════════════════════════════════════════
# 12 — عقود إيجار ECRS ×10 (60 عقد)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء عقود إيجار ECRS... (Creating Ejar ECRS contracts...)")

SAR_curr = env['res.currency'].with_context(active_test=False).search([('name','=','SAR')], limit=1)

def ejar_party(contract, role, entity_type, full_name_ar, id_type, id_number,
               mobile, iban=False, nationality='SA', sync_state='pending',
               cr_number=False, unified_number=False):
    # Normalize id_type based on id_number where possible to satisfy model validation
    if id_number:
        s = str(id_number)
        if re.fullmatch(r'1\d{9}', s):
            id_type = 'national_id'
        elif re.fullmatch(r'2\d{9}', s):
            id_type = 'iqama'

    vals = {'contract_id':contract.id,'role':role,'entity_type':entity_type,'full_name_ar':full_name_ar,'id_type':id_type,'id_number':id_number,'mobile':mobile,'nationality':nationality}
    if iban:           vals['iban']           = iban
    if cr_number:      vals['cr_number']      = cr_number
    if unified_number: vals['unified_number'] = unified_number
    rec = env['ejar.contract.party'].create(vals)
    if sync_state != 'pending': rec.write({'sync_state': sync_state})
    return rec

def ejar_unit(contract, property_rec, unit_number, unit_type, area,
              floor_number=0, bedrooms=0, bathrooms=0, finishing='finished',
              furnishing='unfurnished', sync_state='pending'):
    rec = env['ejar.contract.unit'].create({'contract_id':contract.id,'property_id':property_rec.id,'unit_number':unit_number,'unit_type':unit_type,'area':area,'floor_number':floor_number,'bedrooms':bedrooms,'bathrooms':bathrooms,'finishing':finishing,'furnishing':furnishing})
    if sync_state != 'pending': rec.write({'sync_state': sync_state})
    return rec

def sync_log(contract, action, direction, endpoint, http_method, http_status, duration_ms, status='success', request_body=None, response_body=None, error_message=None):
    return env['ejar.sync.log'].create({'company_id':company.id,'contract_id':contract.id,'action':action,'direction':direction,'http_method':http_method,'endpoint':endpoint,'http_status':http_status,'duration_ms':duration_ms,'status':status,'request_body':request_body or False,'response_body':response_body or False,'error_message':error_message or False})

for batch_idx in range(10):
    props   = all_props[batch_idx]
    tens    = all_tenancies[batch_idx]
    owners  = all_owners[batch_idx]
    tenants = all_tenants[batch_idx]
    pfx     = f'DEMO-{batch_idx+1:02d}'

    # ec1 — building
    ec1 = env['ejar.contract'].create({'brokerage_profile_id':ejar_profile.id,'tenancy_id':tens[0].id,'contract_type':'residential','contract_sub_type':'main','use_type':'residential_families','start_date':tens[0].start_date,'end_date':tens[0].end_date,'rent_amount':80000.0,'currency_id':SAR_curr.id,'payment_schedule':'quarterly','payment_option':'bank_transfer','sublease_allowed':False,'ejar_fees_paid_by':'brokerage_office','brokerage_fee':2000.0,'brokerage_fee_paid_by':'lessor'})
    ec1.action_start_building()
    ejar_party(ec1,'lessor','individual',owners[0].name, owners[0].sa_id_type or 'national_id', owners[0].sa_national_id or owners[0].sa_cr_number or '1023456789', owners[0].phone or '+966501234001', iban=owners[0].sa_iban or '')
    ejar_party(ec1,'tenant','individual',tenants[0].name, tenants[0].sa_id_type or 'national_id', tenants[0].sa_national_id or '1098765432', tenants[0].phone or '+966503100001')
    ejar_unit(ec1,props[0],'فيلا-رئيسية','villa',450.0,floor_number=0,bedrooms=5,bathrooms=4)

    # ec2 — ready
    ec2 = env['ejar.contract'].create({'brokerage_profile_id':ejar_profile.id,'tenancy_id':tens[2].id,'contract_type':'residential','contract_sub_type':'main','use_type':'residential_families','start_date':tens[2].start_date,'end_date':tens[2].end_date,'rent_amount':48000.0,'currency_id':SAR_curr.id,'payment_schedule':'monthly','payment_option':'mada','sublease_allowed':False,'ejar_fees_paid_by':'brokerage_office','brokerage_fee':1200.0,'brokerage_fee_paid_by':'lessor'})
    ec2.action_start_building()
    ejar_party(ec2,'lessor','individual',owners[0].name, owners[0].sa_id_type or 'national_id', owners[0].sa_national_id or owners[0].sa_cr_number or '1023456789', owners[0].phone or '+966501234001', sync_state='synced')
    ejar_party(ec2,'tenant','individual',tenants[2].name, tenants[2].sa_id_type or 'national_id', tenants[2].sa_national_id or '1067891234', tenants[2].phone or '+966503100003', sync_state='synced')
    ejar_unit(ec2,props[4],'شقة-ملقا','apartment',160.0,floor_number=7,bedrooms=3,bathrooms=2,sync_state='synced')
    ec2.write({'ejar_status':'ready'})

    # ec3 — submitted
    ec3 = env['ejar.contract'].create({'brokerage_profile_id':ejar_profile.id,'tenancy_id':tens[1].id,'contract_type':'residential','contract_sub_type':'main','use_type':'residential_families','start_date':tens[1].start_date,'end_date':tens[1].end_date,'rent_amount':45000.0,'currency_id':SAR_curr.id,'payment_schedule':'quarterly','payment_option':'bank_transfer','sublease_allowed':False,'ejar_fees_paid_by':'brokerage_office','brokerage_fee':1125.0,'brokerage_fee_paid_by':'lessor','ejar_contract_id':f'{pfx}-EJAR-003','ejar_contract_number':f'12345{batch_idx:05d}'})
    ec3.action_start_building()
    ec3.write({'ejar_status':'submitted','ejar_last_sync':today,'submit_attempt':1})
    ejar_party(ec3,'lessor','individual',owners[0].name, owners[0].sa_id_type or 'national_id', owners[0].sa_national_id or owners[0].sa_cr_number or '1023456789', owners[0].phone or '+966501234001', sync_state='synced')
    ejar_party(ec3,'tenant','individual',tenants[1].name, tenants[1].sa_id_type or 'national_id', tenants[1].sa_national_id or '1034512678', tenants[1].phone or '+966503100002', sync_state='synced')
    ejar_unit(ec3,props[3],'شقة-عليا','apartment',140.0,floor_number=3,bedrooms=3,bathrooms=2,sync_state='synced')
    sync_log(ec3,'contract_submit','outbound','/ecrs/api/v1/contracts','POST',200,842,response_body=f'{{"status":"ACCEPTED","contractId":"{pfx}-EJAR-003"}}')

    # ec4 — approved
    ec4 = env['ejar.contract'].create({'brokerage_profile_id':ejar_profile.id,'tenancy_id':tens[4].id,'contract_type':'commercial','contract_sub_type':'main','use_type':'commercial','start_date':tens[4].start_date,'end_date':tens[4].end_date,'rent_amount':120000.0,'currency_id':SAR_curr.id,'payment_schedule':'quarterly','payment_option':'bank_transfer','sublease_allowed':False,'ejar_fees_paid_by':'brokerage_office','brokerage_fee':3000.0,'brokerage_fee_paid_by':'lessor','ejar_contract_id':f'{pfx}-EJAR-004','ejar_contract_number':f'98765{batch_idx:05d}'})
    ec4.action_start_building()
    ec4.write({'ejar_status':'approved','ejar_last_sync':today,'submit_attempt':1,'poll_count':3})
    ejar_party(ec4,'lessor','organization',owners[3].name, owners[3].sa_id_type or 'national_id', owners[3].sa_cr_number or '1010345678', owners[3].phone or '+966114001400', cr_number=owners[3].sa_cr_number or '1010345678', sync_state='synced')
    ejar_party(ec4,'tenant','individual',tenants[4].name, tenants[4].sa_id_type or 'national_id', tenants[4].sa_national_id or '1055443322', tenants[4].phone or '+966503100005', sync_state='synced')
    ejar_unit(ec4,props[8],'مكتب-رئيسي','office',280.0,floor_number=20,bedrooms=0,bathrooms=2,furnishing='furnish_new',sync_state='synced')
    sync_log(ec4,'webhook_received','inbound','/ejar/webhook','POST',200,45,request_body=f'{{"event":"contract.approved","contractNumber":"98765{batch_idx:05d}"}}',response_body='{"received":true}')

    # ec5 — rejected
    ec5 = env['ejar.contract'].create({'brokerage_profile_id':ejar_profile.id,'tenancy_id':tens[3].id,'contract_type':'residential','contract_sub_type':'main','use_type':'residential_families','start_date':tens[3].start_date,'end_date':tens[3].end_date,'rent_amount':42000.0,'currency_id':SAR_curr.id,'payment_schedule':'annual','payment_option':'bank_transfer','sublease_allowed':False,'ejar_fees_paid_by':'brokerage_office','brokerage_fee':1050.0,'brokerage_fee_paid_by':'lessor','ejar_contract_id':f'{pfx}-EJAR-005'})
    ec5.action_start_building()
    ec5.write({'ejar_status':'rejected','ejar_last_sync':today,'submit_attempt':1,'rejection_reason':'بيانات الهوية غير مطابقة'})
    ejar_party(ec5,'lessor','individual',owners[1].name, owners[1].sa_id_type or 'national_id', owners[1].sa_national_id or owners[1].sa_cr_number or '1056789012', owners[1].phone or '+966502234002', sync_state='synced')
    ejar_party(ec5,'tenant','individual',tenants[3].name, tenants[3].sa_id_type or 'national_id', tenants[3].sa_national_id or '2123456789', tenants[3].phone or '+966503100004', sync_state='failed')
    ejar_unit(ec5,props[5],'شقة-حمراء','apartment',130.0,floor_number=2,bedrooms=3,bathrooms=2,sync_state='synced')
    sync_log(ec5,'contract_submit','outbound','/ecrs/api/v1/contracts','POST',422,912,status='error',response_body='{"error":"ID_MISMATCH","message":"بيانات الهوية غير مطابقة"}')

    # ec6 — draft
    ec6 = env['ejar.contract'].create({'brokerage_profile_id':ejar_profile.id,'tenancy_id':tens[8].id,'contract_type':'residential','contract_sub_type':'main','use_type':'residential_families','start_date':tens[8].start_date,'end_date':tens[8].end_date,'rent_amount':110000.0,'currency_id':SAR_curr.id,'payment_schedule':'biannual','payment_option':'bank_transfer','sublease_allowed':False,'ejar_fees_paid_by':'brokerage_office','brokerage_fee':2750.0,'brokerage_fee_paid_by':'lessor'})
    ejar_party(ec6,'lessor','organization',owners[3].name, owners[3].sa_id_type or 'national_id', owners[3].sa_cr_number or '1010345678', owners[3].phone or '+966114001400', cr_number=owners[3].sa_cr_number or '1010345678')
    ejar_party(ec6,'tenant','individual',tenants[0].name, tenants[0].sa_id_type or 'national_id', tenants[0].sa_national_id or '1098765432', tenants[0].phone or '+966503100001')
    ejar_unit(ec6,props[2],'فيلا-نرجس','villa',600.0,floor_number=0,bedrooms=6,bathrooms=5)

    env.cr.commit()

print(f"  ✓ عقود إيجار ECRS (Ejar contracts)")

# ══════════════════════════════════════════════════════════════════════════
# 13 — المستخدمون ×10
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء المستخدمين... (Creating users...)")

def make_user(name, email, partner, groups, password='demo'):
    existing = env['res.users'].search([('login','=',email)], limit=1)
    if existing: return existing
    kw = {'name':name,'login':email,'email':email,'groups_id':[(6,0,groups)],'password':password,'lang':'ar_001','tz':'Asia/Riyadh'}
    if partner: kw['partner_id'] = partner.id
    return env['res.users'].create(kw)

g_manager    = env.ref('sa_security.group_pms_manager').id
g_accountant = env.ref('sa_security.group_pms_accountant').id
g_agent      = env.ref('sa_security.group_pms_agent').id
g_owner      = env.ref('sa_security.group_pms_owner').id
g_tech       = env.ref('sa_security.group_pms_technician').id
g_portal     = env.ref('base.group_portal').id
g_tenant_portal = env.ref('sa_security.group_pms_tenant_portal').id

# موظفون داخليون (مرة واحدة فقط)
make_user('سارة المدير — مدير العقارات',       'manager@propza-demo.sa',    None, [g_manager])
make_user('عمر المحاسب — محاسب العقارات',      'accountant@propza-demo.sa', None, [g_accountant])
make_user('لينا الموظفة — خدمة العملاء',       'agent@propza-demo.sa',      None, [g_agent])
make_user('مستخدم العرض التوضيحي — Demo User', 'demo@demo.com',             None, [g_manager])

# ملاك ×10
for batch_idx, owner_batch in enumerate(all_owners):
    for o in owner_batch:
        sfx = f'-{batch_idx+1}' if batch_idx > 0 else ''
        email = o.email if batch_idx == 0 else o.email.replace('@', f'{sfx}@') if o.email else f'owner{batch_idx}@propza-demo.sa'
        make_user(o.name, email, o, [g_owner])

# فنيون ×10
for batch_idx, tech_batch in enumerate(all_techs):
    for t in tech_batch:
        sfx = f'-{batch_idx+1}' if batch_idx > 0 else ''
        email = t.email if batch_idx == 0 else t.email.replace('@', f'{sfx}@') if t.email else f'tech{batch_idx}@propza-demo.sa'
        make_user(t.name, email, t, [g_tech])

# مستأجرون ×10
for batch_idx, tenant_batch in enumerate(all_tenants):
    for t in tenant_batch:
        make_user(t.name, t.email, t, [g_tenant_portal])

# وسطاء ×10
for batch_idx, broker_batch in enumerate(all_brokers):
    for b in broker_batch:
        sfx = f'-{batch_idx+1}' if batch_idx > 0 else ''
        email = b.email if batch_idx == 0 else b.email.replace('@', f'{sfx}@') if b.email else f'broker{batch_idx}@propza-demo.sa'
        make_user(b.name, email, b, [g_portal])

env.cr.commit()
print(f"  ✓ المستخدمون (Users)")

# ══════════════════════════════════════════════════════════════════════════
# 14 — بيانات الملفات الشخصية للمستأجرين ×10
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء بيانات الملفات الشخصية... (Creating tenant profiles...)")

from datetime import datetime as _dt

PROFILE_DATA = [
    ('male',   '1985-03-15', 'مهندس معماري متخصص في تصميم المباني السكنية.',  r_riyadh,'الرياض','العليا',   '3214','1','4521','12331','REAA3214'),
    ('male',   '1990-07-22', 'مدير مبيعات في شركة تقنية.',                    r_jeddah,'جدة',   'النزهة',   '7821','2','1234','23521','JZNZ7821'),
    ('female', '1988-11-08', 'معلمة في مدرسة ابتدائية حكومية.',               r_riyadh,'الرياض','النرجس',   '5540','4','3312','13312','RNRJ5540'),
    ('female', '1992-04-20', 'موظفة في قطاع الصحة.',                          r_riyadh,'الرياض','الملقا',   '2210','1','8871','13521','RMLQ2210'),
    ('male',   '1979-09-12', 'محاسب قانوني لدى شركة استثمار.',                r_riyadh,'الرياض','الروضة',   '8831','3','2245','11411','RRWD8831'),
    ('female', '1995-01-30', 'مصممة جرافيك مستقلة.',                          r_dammam,'الدمام','الشاطئ',   '4412','2','5561','31441','DSHT4412'),
    ('male',   '1983-06-05', 'طيار في إحدى شركات الطيران الخليجية.',           r_riyadh,'الرياض','الورود',   '6623','1','7712','12711','RWRD6623'),
    ('female', '1991-12-17', 'صيدلانية في مستشفى حكومي.',                     r_jeddah,'جدة',   'الحمراء',  '3345','5','9901','23411','JHMR3345'),
    ('male',   '1987-08-24', 'مقاول بناء يدير مشاريع إنشائية.',               r_riyadh,'الرياض','الصحافة',  '9912','2','3341','12261','RSSH9912'),
    ('female', '1998-05-11', 'طالبة دكتوراه في جامعة الملك عبدالعزيز.',       r_jeddah,'جدة',   'الأندلس',  '1123','7','6612','23631','JAND1123'),
]

now = _dt.now()

def make_verif(partner, id_type, id_number, id_expiry, state, rejection_reason=False):
    rec = env['sa.user.verification'].create({
        'partner_id':   partner.id,
        'id_type':      id_type,
        'id_number':    id_number,
        'id_expiry':    str(id_expiry) if id_expiry else False,
        'state':        state,
        'submission_date': now if state in ('submitted','verified','rejected') else False,
        'verified_date':   now if state == 'verified' else False,
        'rejection_reason': rejection_reason or False,
    })
    if state == 'verified':
        partner.write({'sa_id_type':id_type,'sa_national_id':id_number,'sa_id_expiry':id_expiry,'sa_id_verified':True})
    return rec

def make_doc(partner, doc_type, name, upload_days_ago, expiry_days=None, notes=None):
    env['sa.user.document'].create({
        'partner_id':  partner.id,
        'doc_type':    doc_type,
        'name':        name,
        'upload_date': str(ago(upload_days_ago)),
        'expiry_date': str(ahead(expiry_days)) if expiry_days is not None else False,
        'notes':       notes or False,
    })

VERIF_STATES = [
    ('national_id', ahead(1095), 'verified'),
    ('national_id', ahead(730),  'verified'),
    ('national_id', ahead(548),  'submitted'),
    ('iqama',       ahead(180),  'verified'),
    ('national_id', ago(10),     'rejected'),
    ('national_id', None,        'draft'),
    ('national_id', ahead(1460), 'verified'),
    ('national_id', ahead(365),  'submitted'),
    ('national_id', ahead(912),  'verified'),
    ('national_id', None,        'draft'),
]

for batch_idx, tenant_batch in enumerate(all_tenants):
    for i, tenant_obj in enumerate(tenant_batch):
        gender, dob, bio, rgn, city, district, bldg, unit, addl, postal, short_addr = PROFILE_DATA[i]
        tenant_obj.write({'gender':gender,'date_of_birth':dob,'bio':bio,'sa_region_id':rgn.id if rgn else False,'city':city,'sa_district':district,'sa_building_no':bldg,'sa_unit_no':unit,'sa_additional_no':addl,'sa_postal_code':postal,'sa_national_address':short_addr})

        id_type, id_expiry, state = VERIF_STATES[i]
        nat_id = tenant_obj.sa_national_id or str(1000000000 + batch_idx * 10 + i)
        if state == 'draft':
            env['sa.user.verification'].create({'partner_id':tenant_obj.id,'id_type':id_type,'id_number':nat_id,'state':'draft'})
        elif state == 'rejected':
            make_verif(tenant_obj, id_type, nat_id, id_expiry, 'rejected', rejection_reason='الوثيقة منتهية الصلاحية')
        else:
            make_verif(tenant_obj, id_type, nat_id, id_expiry, state)

        # Documents
        make_doc(tenant_obj, 'national_id', f'هوية وطنية — {tenant_obj.name}', 90, expiry_days=365)
        if i in (0, 6):
            make_doc(tenant_obj, 'other', f'خطاب راتب — {tenant_obj.name}', 30, expiry_days=180)
        elif i in (1, 8):
            make_doc(tenant_obj, 'lease_contract', f'عقد إيجار سابق — {tenant_obj.name}', 200, expiry_days=1460)

    env.cr.commit()

print(f"  ✓ الملفات الشخصية (Tenant profiles)")

# ══════════════════════════════════════════════════════════════════════════
# 15 — بيانات CRM ×10 (100 طلب + جولات)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء بيانات CRM... (Creating CRM leads...)")

_stage_new        = env['sa.crm.stage'].search([('sequence','=',10)], limit=1)
_stage_contacted  = env['sa.crm.stage'].search([('sequence','=',20)], limit=1)
_stage_showing    = env['sa.crm.stage'].search([('sequence','=',30)], limit=1)
_stage_negotiating= env['sa.crm.stage'].search([('sequence','=',40)], limit=1)
_stage_won        = env['sa.crm.stage'].search([('is_won','=',True)],   limit=1)
_stage_lost       = env['sa.crm.stage'].search([('sequence','=',60)],   limit=1)

_user_manager = env['res.users'].search([('login','=','manager@propza-demo.sa')], limit=1)
_user_agent   = env['res.users'].search([('login','=','agent@propza-demo.sa')],   limit=1)

def lead(partner, lead_type, prop_type, stage, user, source, budget_min, budget_max,
         region=None, prop=None, commission=0, deadline_days=None, priority='0',
         state='open', lost_reason=None, description=None):
    vals = {'partner_id':partner.id,'lead_type':lead_type,'property_type':prop_type,'stage_id':stage.id,'user_id':user.id,'source':source,'budget_min':budget_min,'budget_max':budget_max,'preferred_region_id':region.id if region else False,'property_id':prop.id if prop else False,'expected_commission':commission,'date_deadline':str(ahead(deadline_days)) if deadline_days else False,'priority':priority,'state':state,'lost_reason':lost_reason or False,'description':description or False}
    if state == 'lost': vals['active'] = False
    return env['sa.crm.lead'].create(vals)

def showing(crm_lead, prop, scheduled_days, outcome, user, notes=None):
    env['sa.crm.showing'].create({'lead_id':crm_lead.id,'property_id':prop.id,'scheduled_date':str(ago(scheduled_days))+' 10:00:00','user_id':user.id,'outcome':outcome,'notes':notes or False})

LEAD_TEMPLATES = [
    # (tidx, lead_type, prop_type, stage, user_key, source, bmin, bmax, reg_key, pidx, comm, ddays, prio, state, lost_reason, desc)
    (0,'rent','residential', 'negotiating','agent', 'referral',40000,55000,'r',3,2750,14,'1','open',None,'يفضل الطابق الثاني أو أعلى'),
    (1,'rent','commercial',  'showing',    'agent', 'website', 80000,130000,'r',8,6500,30,'1','open',None,None),
    (2,'rent','residential', 'contacted',  'manager','phone',  90000,120000,'j',None,6000,45,'2','open',None,'عائلة كبيرة، تحتاج ٥ غرف على الأقل'),
    (3,'rent','residential', 'new',        'agent', 'social',  30000,45000,'d',None,0,   60,'0','open',None,None),
    (4,'rent','industrial',  'new',        'manager','walkin', 60000,90000,'r',None,0,   None,'0','open',None,'مستودع للتخزين'),
    (6,'rent','commercial',  'contacted',  'agent', 'portal',  35000,50000,'r',None,0,   20,'1','open',None,None),
    (7,'rent','residential', 'won',        'agent', 'referral',40000,55000,'r',4,2400,None,'0','won',None,None),
    (8,'buy', 'residential', 'won',        'manager','website',1200000,1800000,'r',0,54000,None,'2','won',None,None),
    (5,'rent','residential', 'lost',       'agent', 'phone',   35000,50000,'r',None,0,  None,'0','lost','قررت الانتقال إلى جدة',None),
    (9,'rent','commercial',  'lost',       'agent', 'walkin',  70000,100000,'r',None,0,  None,'0','lost','وجد مكتباً عبر طرف ثالث',None),
]

STAGE_MAP = {'new':_stage_new,'contacted':_stage_contacted,'showing':_stage_showing,'negotiating':_stage_negotiating,'won':_stage_won,'lost':_stage_lost}
REG_MAP   = {'r':r_riyadh,'j':r_jeddah,'d':r_dammam}
USER_MAP  = {'manager':_user_manager,'agent':_user_agent}

SHOWING_MAP = {
    0: [(3,5,'done','أعجبه الموقع'),(4,10,'done','لم يعجبه المدخل')],
    1: [(8,3,'done','عرض المكتب'),(9,1,'scheduled','جولة ثانية مجدولة')],
    6: [(4,30,'done','أعجبتها الشقة'),(3,35,'done','الخيار الأول لم يناسبها')],
    7: [(0,45,'done','زار الفيلا مرتين'),(1,50,'done','خيار احتياطي')],
}

for batch_idx in range(10):
    props   = all_props[batch_idx]
    tenants = all_tenants[batch_idx]
    batch_leads = []
    for li, tmpl in enumerate(LEAD_TEMPLATES):
        tidx,ltype,ptype,stage_key,user_key,source,bmin,bmax,reg_key,pidx,comm,ddays,prio,state,lost_reason,desc = tmpl
        prop_obj    = props[pidx] if pidx is not None else None
        region_obj  = REG_MAP.get(reg_key)
        partner_obj = tenants[tidx]
        l = lead(partner_obj,ltype,ptype,STAGE_MAP[stage_key],USER_MAP[user_key],source,bmin,bmax,region=region_obj,prop=prop_obj,commission=comm,deadline_days=ddays,priority=prio,state=state,lost_reason=lost_reason,description=desc)
        if li in SHOWING_MAP:
            for sidx, sdays, outcome, notes in SHOWING_MAP[li]:
                showing(l, props[sidx], sdays, outcome, USER_MAP[user_key], notes)
        batch_leads.append(l)
    env.cr.commit()

print(f"  ✓ طلبات CRM (CRM leads)")

# ══════════════════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════════════════
print("")
print("══════════════════════════════════════════════════════════════")
print("  ✓ تم تحميل البيانات التجريبية ×10 بنجاح!")
print("  ✓ 10x Demo data loaded successfully!")
print("══════════════════════════════════════════════════════════════")
print(f"  الملاك           / Owners:       {env['res.partner'].search_count([('is_property_owner','=',True)])}")
print(f"  المستأجرون       / Tenants:      {env['res.partner'].search_count([('is_tenant','=',True)])}")
print(f"  الوسطاء          / Brokers:      {env['res.partner'].search_count([('is_broker','=',True)])}")
print(f"  الفنيون          / Technicians:  {env['res.partner'].search_count([('is_technician','=',True)])}")
print(f"  العقارات         / Properties:   {env['property.property'].search_count([])}")
print(f"  عقود الإيجار     / Tenancies:    {env['property.tenancy'].with_context(active_test=False).search_count([])}")
print(f"  الدفعات          / Payments:     {env['sa.rent.payment'].search_count([])}")
print(f"  طلبات الصيانة   / Maint Reqs:   {env['sa.maintenance.request'].with_context(active_test=False).search_count([])}")
print(f"  عقود الصيانة    / Maint Conts:  {env['sa.maintenance.contract'].search_count([])}")
print(f"  عمولات الوسطاء  / Commissions:  {env['sa.broker.commission'].search_count([])}")
print(f"  عقود إيجار ECRS / Ejar Conts:   {env['ejar.contract'].search_count([])}")
print(f"  طلبات CRM        / CRM Leads:   {env['sa.crm.lead'].with_context(active_test=False).search_count([])}")
print(f"  جولات ميدانية   / Showings:     {env['sa.crm.showing'].search_count([])}")
print(f"  المستخدمون       / Users:        {env['res.users'].search_count([('share','=',False)])+env['res.users'].search_count([('share','=',True)])}")
print("")
PYEOF

echo ""
echo "  ✓ اكتمل التحميل ×10! Login: demo@demo.com / demo"
echo ""
