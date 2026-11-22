"""Build bilingual (EN/AR) vector documents for Ability CRM navigation.

Source: crawl of https://app.ability-tech.com (EN + AR UI) on 2026-11-12,
signed in as Super Admin (SODIC). Every label below was read from the live UI;
nothing is translated or invented. Where an Arabic label was not captured, it is null.

    python scripts/ingestion/build_vector_docs.py

Output (in data/vector_docs/):
    ability_crm_vector_docs.json   - list of documents (pretty)
"""

import json
from pathlib import Path

BASE_URL = "https://app.ability-tech.com"
OUT = Path(__file__).resolve().parent.parent.parent / "data" / "vector_docs"

# ---------------------------------------------------------------- groups (sidebar order)
GROUPS = [
    ("dashboard", "Dashboard", "لوحة التحكم"),
    ("definition", "Definition", "التعريفات"),
    ("unit", "Unit", "الوحدة"),
    ("unit_blocks", "Unit Blocks", "حظر الوحدات"),
    ("customers", "Customers", "العملاء"),
    ("services", "Services", "الخدمات"),
    ("rental", "Rental", "التأجير"),
    ("tickets", "Tickets", "التذاكر"),
    ("inquiries", "Inquiries", "الاستفسارات"),
    ("complaints", "Complaints & Suggestions", "الشكاوى و الاقتراحات"),
    ("invoices", "Invoices", "الفواتير"),
    ("reports", "Reports", "التقارير"),
    ("users", "Users", "المستخدمين"),
    ("roles", "Roles", "الأدوار"),
    ("document_library", "DocumentLibrary", "مكتبة المستندات"),
    ("settings", "Settings", "الاعدادات"),
    ("ownership", "Ownership Managment", "إدارة الملكية"),
    ("imports", "Imports", "الاستيراد"),
    ("notifications", "Notifications", "الإشعارات"),
]
GROUP = {k: {"en": en, "ar": ar} for k, en, ar in GROUPS}

# ---------------------------------------------------------------- shared label lists
ACTIVE_TABS = [("All", "الكل"), ("Active", "نشط"), ("Inactive", "غير نشط")]
DASH_TABS = [("Statistics", "الإحصائيات"), ("Tickets", "التذاكر"), ("Complaints", "الشكاوى")]
UNIT_SEARCH_FILTERS = (["Unit Number", "Exact Match"], ["رقم الوحدة", "مطابقة تامة"])
UNIT_SEARCH_FILTERS_ID = (["Unit Number", "Unit ID", "Exact Match"], None)
UNIT_COLS_EN = ["Unit Number", "Project Name", "Sub Project Code", "Unit Type", "Total Owners", "Address", "Total Area",
                "Floor", "Furnished", "Active", "Eligible for Rent", "Rental Company", "Locked", "Locked By",
                "Customer Name", "Mobile Number", "Sign Date"]
UNIT_COLS_AR = ["رقم الوحدة", "اسم المشروع", "كود المشروع الفرعي", "نوع الوحدة", "إجمالي الملاك", "العنوان", "المساحة الكلية",
                "الطابق", "مفروشة", "نشطة", "مؤهل للإيجار", "شركة الإيجار", "محظورة", "محظورة بواسطة",
                "اسم العميل", "رقم الجوال", "تاريخ التوقيع"]
BLOCK_COLS_EN = ["Unit Number", "Blocked", "Legal Block", "Finance Block", "Project Name", "Unit Type", "Total Owners",
                 "Address", "Total Area", "Floor", "Furnished", "Active", "Eligible for Rent", "Rental Company",
                 "Blocked By", "Customer Name", "ID Number", "Mobile Number", "Sign Date"]
BLOCK_COLS_AR = ["رقم الوحدة", "محظورة", "حظر قانوني", "حظر مالي", "اسم المشروع", "نوع الوحدة", "إجمالي الملاك",
                 "العنوان", "المساحة الكلية", "الطابق", "مفروشة", "نشطة", "مؤهل للإيجار", "شركة الإيجار",
                 "تم الحظر بواسطة", "اسم العميل", "رقم الهوية", "رقم الجوال", "تاريخ التوقيع"]
INVOICE_DATES_EN = ["Pending Date", "Collected Date", "Void Date", "Under Payment Process Date", "Void Requested Date",
                    "Partially Collected Date", "Refunded Date", "Refund Requested Date", "Partially Refunded Date",
                    "Runner Cashier"]
INVOICE_DATES_AR = ["تاريخ التعليق", "تاريخ التحصيل", "تاريخ الإلغاء", "تاريخ قيد الدفع", "تاريخ طلب الإلغاء",
                    "تاريخ التحصيل الجزئي", "تاريخ الاسترداد", "تاريخ طلب الاسترداد", "تاريخ الاسترداد الجزئي",
                    "كاشير متنقل"]


def A(spec: str):
    """'Search=بحث|Clear=مسح' -> [{'en':..,'ar':..}]"""
    out = []
    for part in filter(None, spec.split("|")):
        en, _, ar = part.partition("=")
        out.append({"en": en, "ar": ar or None})
    return out


SEARCH_CLEAR = "Search=بحث|Clear=مسح"
SC_COLS = SEARCH_CLEAR + "|Columns=الأعمدة"
SC_EXPORT = SEARCH_CLEAR + "|Export to Excel=تصدير إلى إكسل|Columns=الأعمدة"
DEF_ACTIONS = "Add=إضافة|Search=بحث|Columns=الأعمدة|Edit=تعديل"

# ---------------------------------------------------------------- forms reached from "Add ..." screens
# Each Add screen first asks for a unit (search by unit number), then the user clicks the result row.
FORMS = {
    "unit_blocks.add_block": dict(
        url="/en/unit-blocks/add/create",
        title=("Unit Blocks - Block Details", "حظر الوحدات - تفاصيل الحظر"),
        tabs=[("Finance", "مالي"), ("Legal", "قانوني")],
        fields=(["Unit Number", "Project Name", "Unit Type", "Customer Name", "Mobile Number", "Reason *", "Attachments"],
                ["رقم الوحدة", "اسم المشروع", "نوع الوحدة", "اسم العميل", "رقم الجوال", "السبب *", "المرفقات"]),
        actions="Show Attachments=عرض المرفقات|Block Unit=حظر الوحدة|Save Changes=حفظ التغييرات|Cancel=إلغاء",
        result_cols=(BLOCK_COLS_EN, BLOCK_COLS_AR),
    ),
    "rental.add_rental": dict(
        url="/en/rentals/add/create",
        title=("Booking Details", "تفاصيل الحجز"),
        via=("Add Reservation", None),
        fields=(["Unit Number", "Current Customer", "Rental Company *", "Tenant Name *", "Gender", "ID Type *",
                 "ID Number *", "Email", "Phone Number *", "Check-in Date *", "Check-out Date *",
                 "Total Tenants Count *", "Access Card Number (Optional)", "Notes", "Attachments",
                 "Tenant Attachments *"],
                ["رقم الوحدة", "العميل الحالي", "شركة الإيجار *", "اسم المستأجر *", "الجنس", "نوع الهوية *",
                 "رقم الهوية *", "البريد الإلكتروني", "رقم الهاتف *", "تاريخ تسجيل الدخول *", "تاريخ تسجيل الخروج *",
                 "إجمالي عدد السكان *", "رقم كارت الدخول (اختياري)", "ملاحظات", "المرفقات", "مرفقات المستأجر *"]),
        actions="Add Relative=إضافة قريب|Save=حفظ|Cancel=إلغاء",
        result_cols=(["Unit Number", "Customer Name", "Customer Code", "Mobile Number", "Actions"],
                     ["رقم الوحدة", "اسم العميل", "كود العميل", "رقم الجوال", "الإجراءات"]),
        result_actions="Add Reservation=|View Rental History=",
    ),
    "tickets.add_cts": dict(
        url="/en/tickets/cts/add/create",
        title=("Create CTS Record", "إنشاء سجل CTS"),
        fields=(["Unit Number *", "Customer Code *", "Customer Name", "Customer Mobile", "Mobile", "Annual Fees *",
                 "Invoice Types *", "Collected Amount", "Contracts Status", "Update Status", "Old", "Receiver", "Notes",
                 "Internet Activation Date", "Internet Annual Fees", "Internet Annual Fees Status", "Internet Status",
                 "IP TV Activation Date", "IP TV Annual Fees", "IP TV Annual Fees Status", "IP TV MAC Address",
                 "IP TV Miss Payment", "IP TV Multipoint", "IP TV Package", "IP TV Status", "IP Phone Activation Date",
                 "IP Phone Status", "IP Phone MAC", "IP Phone Internet Fees", "Hotbird Receiving Date",
                 "Nilesat Receiving Date", "Receiving Dorm Status", "SMA TV Receiving Date", "SMA TV Contract Date",
                 "SMA TV Contract Value", "SMA TV Annual Fees Status", "SMA TV Payment Status",
                 "SMA TV Additional Point", "SMA TV Multipoint", "SMA TV Multi Point Receiving Date", "SMA TV Extra"],
                ["رقم الوحدة *", "كود العميل *", "اسم العميل", "جوال العميل", "الجوال", "الرسوم السنوية *",
                 "أنواع الفواتير *", "المبلغ المحصل", "حالة العقود", "حالة التحديث", "قديم", "المستقبل", "ملاحظات",
                 "تاريخ تفعيل الإنترنت", "رسوم الإنترنت السنوية", "حالة رسوم الإنترنت السنوية", "حالة الإنترنت",
                 "تاريخ تفعيل IP TV", "رسوم IP TV السنوية", "حالة رسوم IP TV السنوية", "عنوان MAC لـ IP TV",
                 "دفعة مفقودة IP TV", "IP TV متعدد النقاط", "باقة IP TV", "حالة IP TV", "تاريخ تفعيل IP Phone",
                 "حالة IP Phone", "عنوان MAC لـ IP Phone", "رسوم إنترنت IP Phone", "تاريخ استقبال Hotbird",
                 "تاريخ استقبال Nilesat", "حالة استقبال السكن", "تاريخ استقبال SMA TV", "تاريخ عقد SMA TV",
                 "قيمة عقد SMA TV", "حالة رسوم SMA TV السنوية", "حالة دفع SMA TV", "نقطة إضافية SMA TV",
                 "SMA TV متعدد النقاط", "تاريخ استقبال النقاط المتعددة SMA TV", "إضافي SMA TV"]),
        actions="Submit=إرسال|Create & Collect=إنشاء وتحصيل|Cancel=إلغاء",
        result_cols=(["Unit Number", "Customer Name", "Customer Mobile", "Project"],
                     ["رقم الوحدة", "اسم العميل", "جوال العميل", "المشروع"]),
    ),
    "tickets.add_ticket": dict(
        url="/en/tickets/add/create",
        title=("Tickets - Create Ticket", "التذاكر - إنشاء تذكرة"),
        fields=(["Customer Name", "Mobile Number", "Unit Type", "Unit Number", "Area", "Location", "Requester Name *",
                 "Requester Mobile *", "Department *", "Contact Channel", "Arrival Date", "Notes", "Arrival Time",
                 "Runner Cashier", "Urgent", "Services", "Select Services", "Attach Document"],
                ["اسم العميل", "رقم الجوال", "نوع الوحدة", "رقم الوحدة", "المساحة", "الموقع", "اسم مقدم الطلب *",
                 "جوال مقدم الطلب *", "القسم *", "قناة التواصل", "تاريخ الوصول", "ملاحظات", "وقت الوصول",
                 "كاشير متنقل", "عاجل", "الخدمات", "اختر الخدمات", "إرفاق مستند"]),
        actions="Add Service=إضافة خدمة|Attach Document=إرفاق مستند|Add=إضافة|Create & Collect=إنشاء وتحصيل|Cancel=إلغاء",
        result_cols=(["Unit Number", "Customer Name", "Project Name", "Mobile", "Email", "Date of Birth", "Locked"],
                     ["رقم الوحدة", "اسم العميل", "اسم المشروع", "الجوال", "البريد الإلكتروني", "تاريخ الميلاد", "محظورة"]),
    ),
    "inquiries.add_inquiry": dict(
        url="/en/inquiries/add",
        title=("Add Inquiry", "إضافة استفسار"),
        fields=(["Unit Number *", "Requester Name *", "Requester Mobile *", "Contact Channel *", "Inquiry *", "Response *"],
                ["رقم الوحدة *", "اسم مقدم الطلب *", "جوال مقدم الطلب *", "قناة التواصل *", "الاستفسار *", "الرد *"]),
        actions="Add=إضافة|Cancel=إلغاء",
        result_cols=(["Unit Number", "Customer Name", "Project Name", "Mobile"],
                     ["رقم الوحدة", "اسم العميل", "اسم المشروع", "الجوال"]),
    ),
    "complaints.add_complaint": dict(
        url="/en/complaints/add/create",
        title=("Complaints - Create Complaint", "الشكاوى - إنشاء شكوى"),
        fields=(["Customer Name", "Customer Code", "Mobile Number", "Unit Number", "Project", "Department",
                 "Complaint Type *", "Complaint Status *", "Contact Channel *", "Complaint Date *", "Details *"],
                ["اسم العميل", "كود العميل", "رقم الجوال", "رقم الوحدة", "المشروع", "القسم",
                 "نوع الشكوى *", "حالة الشكوى *", "قناة التواصل *", "تاريخ الشكوى *", "التفاصيل *"]),
        actions="Add=إضافة|Cancel=إلغاء",
        result_cols=(["Unit Number", "Customer Name", "Project Name", "Mobile", "Email", "Date of Birth"],
                     ["رقم الوحدة", "اسم العميل", "اسم المشروع", "الجوال", "البريد الإلكتروني", "تاريخ الميلاد"]),
    ),
    "invoices.add_invoice": dict(
        url="/en/invoices/create",
        title=("Create Invoice", "إنشاء فاتورة"),
        fields=(["Unit Number *", "Customer Name", "Invoice Type *", "Contact Channel", "Amount *", "Notes"],
                ["رقم الوحدة *", "اسم العميل", "نوع الفاتورة *", "قناة التواصل", "المبلغ *", "ملاحظات"]),
        actions="EGP Show Debt=EGP عرض المديونية|Add=إضافة|Create & Collect=إنشاء وتحصيل|Cancel=إلغاء",
        result_cols=(["Unit", "Customer", "Project", "Mobile"], ["الوحدة", "العميل", "المشروع", "الجوال"]),
    ),
    "ownership.add_request": dict(
        url="/en/ownership-management/add",
        title=("New Ownership Management Request", "طلب إدارة ملكية جديد"),
        fields=(["Category *", "Description *", "Attachments *"], ["الفئة *", "الوصف *", "المرفقات *"]),
        actions="Add=إضافة|Cancel=إلغاء",
        result_cols=(["Unit Number", "Customer Name", "Project Name", "Mobile Number"],
                     ["رقم الوحدة", "اسم العميل", "اسم المشروع", "رقم الجوال"]),
    ),
}

# ---------------------------------------------------------------- screens (sidebar items)
S = []


def screen(group, sid, en, ar, url, title, filters=None, columns=None, tabs=None, actions="", **extra):
    S.append(dict(group=group, id=f"{group}.{sid}", en=en, ar=ar, url=url, title=title, filters=filters,
                  columns=columns, tabs=tabs or [], actions=actions, **extra))


T_COLS = (["Status", "SLA", "Delayed", "Urgent", "Ticket ID", "Customer Name", "Requester Name", "Unit Number",
           "Department", "Services", "Arrival Time", "Last Status", "Request From"],
          ["الحالة", "متأخرة", "التأخير", "عاجل", "رقم التذكرة", "اسم العميل", "اسم مقدم الطلب", "رقم الوحدة",
           "القسم", "الخدمات", "وقت الوصول", "آخر حالة", "مصدر الطلب"])
C_COLS = (["Complaint ID", "Unit Number", "Customer Name", "Mobile Number", "Department", "Type", "Status",
           "Request From", "Complaint Date", "Created By"],
          ["رقم الشكوى", "رقم الوحدة", "اسم العميل", "رقم الجوال", "القسم", "النوع", "الحالة", "مصدر الطلب",
           "تاريخ الشكوى", "أنشئ بواسطة"])

# Dashboard
screen("dashboard", "complaints", "Complaints", "الشكاوى و الإقتراحات", "/en/dashboard/complaints", ("Complaints", "الشكاوى"),
       columns=C_COLS, tabs=DASH_TABS, actions="Columns=الأعمدة")
screen("dashboard", "statistics", "Statistics", "الإحصائيات", "/en/dashboard/statistics", ("Statistics", "الإحصائيات"),
       filters=(["Period", "Date"], ["الفترة", "التاريخ"]), tabs=DASH_TABS,
       sections=(["Tickets", "Collected Invoices", "SLA & Delay", "Complaints by Status", "Tickets by Department"],
                 ["التذاكر", "الفواتير المحصلة", "اتفاقية الخدمة والتأخير", "الشكاوى حسب الحالة", "التذاكر حسب القسم"]))
screen("dashboard", "tickets", "Tickets", "التذاكر", "/en/dashboard/tickets", ("Tickets", "التذاكر"),
       columns=T_COLS, tabs=DASH_TABS, actions="Columns=الأعمدة")

# Definition
NAME_COLS = (["#", "Name", "Actions"], ["#", "الاسم", "الإجراءات"])
BYNAME = (["Search by name..."], None)
screen("definition", "department", "Department", "القسم", "/en/definitions/department", ("Department", "القسم"),
       filters=BYNAME, columns=NAME_COLS, tabs=ACTIVE_TABS, actions=DEF_ACTIONS + "|Delete=حذف")
screen("definition", "erp_codes", "ERP Codes", "اكواد الساب", "/en/definitions/erp-codes", ("ERP account code", "كود الحساب في ERP"),
       filters=(["Search by code...", "Search by name..."], None),
       columns=(["#", "Code", "Name", "Actions"], ["#", "الكود", "الاسم", "الإجراءات"]), actions=DEF_ACTIONS)
screen("definition", "invoice_types", "Invoice Types", "أنواع الفواتير", "/en/definitions/invoice-types", ("Invoice Types", "أنواع الفواتير"),
       filters=BYNAME, columns=(["#", "Name", "Description", "ERP account code", "Actions"],
                                ["#", "الاسم", "الوصف", "كود الحساب في ERP", "الإجراءات"]),
       tabs=ACTIVE_TABS, actions=DEF_ACTIONS + "|Export to Excel=تصدير إلى إكسل")
screen("definition", "location", "Location", "الموقع", "/en/definitions/location", ("Locations", "المواقع"),
       filters=BYNAME, columns=NAME_COLS, tabs=ACTIVE_TABS,
       actions="Add Root Location=إضافة موقع رئيسي|Add Sub-Location=إضافة موقع فرعي|Search=بحث|Columns=الأعمدة|Edit=تعديل|Delete=حذف")
screen("definition", "location_type", "Location Type", "نوع الموقع", "/en/definitions/location-type", ("Location Types", "أنواع المواقع"),
       filters=BYNAME, columns=NAME_COLS, tabs=ACTIVE_TABS, actions=DEF_ACTIONS + "|Delete=حذف")
screen("definition", "positions", "Positions", "الوظائف", "/en/definitions/positions", ("Position", "المنصب"),
       filters=BYNAME, columns=NAME_COLS, tabs=ACTIVE_TABS, actions=DEF_ACTIONS)
screen("definition", "rental_companies", "Rental Companies", "شركات التأجير", "/en/definitions/rental-companies",
       ("Rental Companies", "شركات التأجير"), filters=BYNAME,
       columns=(["Name", "Commercial Register", "Tax Register", "Description"],
                ["الاسم", "السجل التجاري", "السجل الضريبي", "الوصف"]),
       tabs=ACTIVE_TABS, actions="Add=إضافة|Search=بحث|Columns=الأعمدة")
screen("definition", "sister_companies", "Sister Companies", "الشركات الشقيقة", "/en/definitions/sister-companies",
       ("Sister Companies", "الشركات الشقيقة"), filters=BYNAME, columns=NAME_COLS, tabs=ACTIVE_TABS,
       actions="Add=إضافة|Search=بحث|Columns=الأعمدة")
screen("definition", "unit_block_categories", "Unit Block Categories", "فئات حظر الوحدات",
       "/en/definitions/unit-block-categories", ("Unit Block Categories", "فئات حظر الوحدات"), filters=BYNAME,
       columns=(["#", "Name", "Scope", "Actions"], ["#", "الاسم", "النطاق", "الإجراءات"]), tabs=ACTIVE_TABS,
       actions=DEF_ACTIONS)

# Unit (single item)
screen("unit", "search", "Unit", "الوحدة", "/en/units/search", ("Units - Search", "الوحدات - بحث"),
       filters=(["Unit Number", "Exact Match", "Project", "Active", "Locked", "Furnished", "Eligible for Rent",
                 "Rental Company", "Delivery Date"],
                ["رقم الوحدة", "مطابقة تامة", "المشروع", "نشط", "محظورة", "مفروشة", "مؤهل للإيجار", "شركة الإيجار",
                 "تاريخ التسليم"]),
       columns=(UNIT_COLS_EN, UNIT_COLS_AR), actions=SC_EXPORT,
       row_opens="unit.details", is_group_item=True)

# Unit Blocks
screen("unit_blocks", "add_block", "Add Block", "إضافة حظر", "/en/unit-blocks/add", ("Block Unit", "حظر وحدة"),
       filters=UNIT_SEARCH_FILTERS_ID, actions=SEARCH_CLEAR, form="unit_blocks.add_block")
screen("unit_blocks", "search_block", "Search Block", "بحث عن حظر", "/en/unit-blocks/search",
       ("Unit Blocks - Search", "حظر الوحدات - بحث"),
       filters=(["Unit Number", "Unit ID", "Block Type", "Exact Match"],
                ["رقم الوحدة", "رقم الوحدة التعريفي", "نوع الحظر", "مطابقة تامة"]),
       columns=(BLOCK_COLS_EN, BLOCK_COLS_AR), tabs=[("All", "الكل"), ("Finance", "مالي"), ("Legal", "قانوني")],
       actions=SC_COLS,
       tab_details={
           "Finance": dict(filters=["Unit Number", "Unit ID", "Project", "Customer Name", "Customer Mobile", "From Date",
                                    "To Date", "Exact Match"],
                           columns=["ID", "Unit Number", "History", "Project Name", "Sub Project Code", "Reason",
                                    "Blocked By", "Blocked Date", "Unblocked By", "Unblocked Date", "Status",
                                    "Customer Name", "Customer Mobile"]),
           "Legal": dict(filters=["Unit Number", "Unit ID", "Category", "Project", "Customer Name", "Customer Mobile",
                                  "Assigned Lawyer", "From Date", "To Date", "Exact Match"],
                         columns=["ID", "Unit Number", "History", "Project Name", "Sub Project Code", "Category",
                                  "Reason", "Blocked By", "Blocked Date", "Unblocked By", "Unblocked Date", "Status",
                                  "Customer Name", "Customer Mobile"]),
       })

# Customers
screen("customers", "relative_requests", "Relative Requests", "صلة القرابة", "/en/customers/relative-requests",
       ("Customers - Search Relative Requests", "العملاء - بحث طلبات الأقارب"),
       filters=(["Request #", "Owner ID", "Unit Number", "Owner Phone Number", "Relative ID Number", "Project", "Status"],
                ["رقم الطلب", "رقم المالك", "رقم الوحدة", "رقم هاتف المالك", "رقم هوية القريب", "المشروع", "الحالة"]),
       columns=(["Request #", "Request Date", "Owner Name", "Owner Code", "Owner ID #", "Unit Number", "Relative Name",
                 "Relation", "ID Type", "Relative ID #", "Phone", "Email", "Media", "Status", "Action By", "Actions"],
                ["رقم الطلب", "تاريخ الطلب", "اسم المالك", "كود المالك", "رقم هوية المالك", "رقم الوحدة", "اسم القريب",
                 "صلة القرابة", "نوع الهوية", "رقم هوية القريب", "الهاتف", "البريد الإلكتروني", "الوسائط", "الحالة",
                 "تم الإجراء بواسطة", "الإجراءات"]),
       actions=SC_EXPORT + "|Show Media=عرض الوسائط|Cancel=إلغاء القبول|Accept=قبول|Reject=رفض")
screen("customers", "search_customer", "Search Customer", "بحث عميل", "/en/customers/search",
       ("Customers - Search", "العملاء - بحث"),
       filters=(["Name", "Code", "ID Number", "Phone", "Unit Number", "Ownership"],
                ["الاسم", "الرمز", "رقم الهوية", "الهاتف", "رقم الوحدة", "نوع الملكية"]),
       columns=(["Customer Name", "Customer Type", "Mobile Number", "Customer Code", "Unit Number", "ID Type",
                 "ID Number", "Contract End Date"],
                ["اسم العميل", "نوع العميل", "رقم الجوال", "كود العميل", "رقم الوحدة", "نوع الهوية", "رقم الهوية",
                 "تاريخ انتهاء العقد"]),
       actions=SC_EXPORT, row_opens="customers.details")

# Services
screen("services", "add_service", "Add Service", "إضافة خدمة", "/en/services/add", ("Services - Add", "الخدمات - إضافة"),
       form_fields=(["English Service Name *", "Arabic Service Name *", "Department *", "ERP account code", "Description",
                     "Price *", "Start Date", "Status *", "Show in mobile (Yes/No)"],
                    ["اسم الخدمة بالإنجليزية *", "اسم الخدمة بالعربية *", "القسم *", "كود الحساب في ERP", "الوصف",
                     "السعر *", "تاريخ البدء", "الحالة *", None]),
       actions="Add=إضافة|Clear=مسح")
screen("services", "service_search", "Service Search", "بحث خدمة", "/en/services/search", ("Services - Search", "الخدمات - بحث"),
       filters=(["Service ID", "Service Name", "Department", "Start Date", "Active (Yes/No)", "Show in mobile (Yes/No)"],
                ["معرف الخدمة", "اسم الخدمة", "القسم", "تاريخ البدء", None, None]),
       columns=(["Edit", "Status", "Delete", "Service ID", "Service Name", "Department", "Description",
                 "ERP account code", "Price", "Created at", "Active"],
                ["تعديل", "الحالة", "حذف", "معرف الخدمة", "اسم الخدمة", "القسم", "الوصف", "كود الحساب في ERP",
                 "السعر", "تاريخ الإنشاء", "نشط"]),
       actions=SC_EXPORT)

# Rental
screen("rental", "add_rental", "Add Rental", "اضافة مستإجر", "/en/rentals/add", ("Rentals - Add", "الإيجارات - إضافة"),
       filters=UNIT_SEARCH_FILTERS, actions=SEARCH_CLEAR, form="rental.add_rental")
screen("rental", "broker_attachments", "Broker Attachments", "مستندات الوسيط", "/en/rentals/rentals-walk-in",
       ("Rentals Walk-In Upload", "رفع إيجارات المشي المباشر"),
       form_fields=(["Rental Company", "Units Excel File", "Delegates Excel File"],
                    ["شركة الإيجار", "ملف إكسل الوحدات", "ملف إكسل المندوبين"]),
       actions="Download Units Template=تحميل قالب الوحدات|Download Delegates Template=تحميل قالب المندوبين|Save=حفظ|Clear=مسح")
screen("rental", "rental_requests", "Rental Requests", "طلبات التأجير", "/en/rentals/rental-requests",
       ("Rentals - Rental Requests", "الإيجارات - طلبات الإيجار"),
       filters=(["Reference Number", "Unit Number", "Tenant Name", "ID Number", "Source", "Status", "Delegate Name",
                 "Delegate NID"],
                ["رقم المرجع", "رقم الوحدة", "اسم المستأجر", "رقم الهوية", "المصدر", "الحالة", "اسم المندوب",
                 "رقم هوية المندوب"]),
       columns=(["Reference Number", "Source", "Project Name", "Unit Number", "Tenant Name", "Delegate Name",
                 "Tenant Mobile", "Review Status"],
                ["رقم المرجع", "المصدر", "اسم المشروع", "رقم الوحدة", "اسم المستأجر", "اسم المندوب", "جوال المستأجر",
                 "حالة المراجعة"]),
       actions=SC_COLS)
screen("rental", "search_rentals", "Search Rentals", "بحث الإيجارات", "/en/rentals/search",
       ("Rentals - Search Rentals", "الإيجارات - بحث الإيجارات"),
       filters=(["Unit Number", "Tenant Name", "Mobile Number", "ID Number", "Project", "Status", "Start Date",
                 "Check-out Date"],
                ["رقم الوحدة", "اسم المستأجر", "رقم الجوال", "رقم الهوية", "المشروع", "الحالة", "تاريخ البداية",
                 "تاريخ الخروج"]),
       columns=(["Accept Request Date", "Check-in Date", "Check-out Date", "Unit Number", "Tenant Name",
                 "Tenant Mobile", "Request Source", "Status"],
                ["تاريخ إنشاء الطلب", "تاريخ تسجيل الدخول", "تاريخ الخروج", "رقم الوحدة", "اسم المستأجر",
                 "جوال المستأجر", "مصدر الطلب", "الحالة"]),
       actions=SC_COLS)

# Tickets
screen("tickets", "add_cts", "Add CTS", "نظام CTS", "/en/tickets/cts/add", ("CTS - Add", "CTS - إضافة"),
       filters=UNIT_SEARCH_FILTERS, actions=SEARCH_CLEAR, form="tickets.add_cts")
screen("tickets", "add_ticket", "Add Ticket", "إضافة تذكرة", "/en/tickets/add", ("Tickets - Add", "التذاكر - إضافة"),
       filters=UNIT_SEARCH_FILTERS, actions=SEARCH_CLEAR, form="tickets.add_ticket")
screen("tickets", "search_cts", "Search CTS", "بحث نظام CTS", "/en/tickets/cts/search", ("CTS - Search", "CTS - بحث"),
       filters=(["Unit Number"], ["رقم الوحدة"]),
       columns=(["Edit", "Print", "CTS ID", "Unit Number", "Customer Code", "Customer Name", "Customer Mobile",
                 "Annual Fees", "Collected Amount", "Contracts Status", "Internet Status", "IP TV Status",
                 "IP Phone Status", "Update Status"],
                ["تعديل", "طباعة", "رقم CTS", "رقم الوحدة", "كود العميل", "اسم العميل", "جوال العميل",
                 "الرسوم السنوية", "المبلغ المحصل", "حالة العقود", "حالة الإنترنت", "حالة IP TV", "حالة IP Phone",
                 "حالة التحديث"]),
       actions=SC_COLS)
screen("tickets", "search_tickets", "Search Tickets", "بحث التذاكر", "/en/tickets/search", ("Tickets - Search", "التذاكر - بحث"),
       filters=(["Ticket ID", "Department", "Service", "User", "Action Taken", "Customer Filter", "Requester Name",
                 "Unit Number", "Date From", "Date To", "Request From", "Contact Channel"],
                ["رقم التذكرة", "القسم", "الخدمة", "المستخدم", "الإجراء المتخذ", "تصفية العملاء", "اسم مقدم الطلب",
                 "رقم الوحدة", "من تاريخ", "إلى تاريخ", "مصدر الطلب", "قناة التواصل"]),
       columns=(["Edit", "Print", "Status", "SLA", "Delayed", "Urgent", "Ticket ID", "Customer Name", "Requester Name",
                 "Requester Mobile", "Unit Number", "Department", "Services", "Notes", "Arrival Time",
                 "Actual Arrival Time", "Duration", "Last Status", "Request From", "Contact Channel", "Seen By",
                 "Agent Name", "Collected By", "Done By", "Created By", "Creation Date"],
                ["تعديل", "طباعة", "الحالة", "متأخرة", "التأخير", "عاجل", "رقم التذكرة", "اسم العميل", "اسم مقدم الطلب",
                 "جوال مقدم الطلب", "رقم الوحدة", "القسم", "الخدمات", "ملاحظات", "وقت الوصول", "وقت الوصول الفعلي",
                 "المدة", "آخر حالة", "مصدر الطلب", "قناة التواصل", "شوهد بواسطة", "اسم الوكيل", "تم التحصيل بواسطة",
                 "تم بواسطة", "تم الإنشاء بواسطة", "تاريخ الإنشاء"]),
       actions=SC_EXPORT)

# Inquiries
screen("inquiries", "add_inquiry", "Add Inquiry", "إضافة استفسار", "/en/inquiries/add", ("Inquiries - Add", "الاستفسارات - إضافة"),
       filters=UNIT_SEARCH_FILTERS_ID, actions=SEARCH_CLEAR, form="inquiries.add_inquiry")
screen("inquiries", "search_inquiry", "Search Inquiry", "بحث استفسار", "/en/inquiries/search",
       ("Inquiries - Search", "الاستفسارات - بحث"),
       filters=(["Unit Number", "Requester Name", "Requester Mobile", "Contact Channel", "Date From", "Date To"],
                ["رقم الوحدة", "اسم مقدم الطلب", "جوال مقدم الطلب", "قناة التواصل", "من تاريخ", "إلى تاريخ"]),
       columns=(["ID", "Unit Number", "Requester Name", "Requester Mobile", "Contact Channel", "Inquiry", "Response",
                 "Date", "Created By"],
                ["معرف", "رقم الوحدة", "اسم مقدم الطلب", "جوال مقدم الطلب", "قناة التواصل", "الاستفسار", "الرد",
                 "التاريخ", "بواسطة"]),
       actions=SC_COLS)

# Complaints & Suggestions
screen("complaints", "add_complaint", "Add Complaint", "إضافة شكوى", "/en/complaints/add", ("Complaints - Add", "الشكاوى - إضافة"),
       filters=UNIT_SEARCH_FILTERS_ID, actions=SEARCH_CLEAR, form="complaints.add_complaint")
screen("complaints", "search_complaint", "Search Complaint", "بحث شكوى", "/en/complaints/search",
       ("Complaints - Search", "الشكاوى - بحث"),
       filters=(["Department", "Complaint Type", "Customer Filter", "Unit Number", "Complaint Status", "Request From",
                 "Contact Channel", "Date From", "Date To"],
                ["القسم", "نوع الشكوى", "تصفية العملاء", "رقم الوحدة", "حالة الشكوى", "مصدر الطلب", "قناة التواصل",
                 "من تاريخ", "إلى تاريخ"]),
       columns=(["Actions", "Complaint ID", "Unit Number", "Customer Name", "Customer Code", "Mobile Number",
                 "Department", "Type", "Status", "Project", "Request From", "Contact Channel", "Complaint Date",
                 "Details", "Responses", "Created By"],
                ["الإجراءات", "رقم الشكوى", "رقم الوحدة", "اسم العميل", "كود العميل", "رقم الجوال", "القسم", "النوع",
                 "الحالة", "المشروع", "مصدر الطلب", "قناة التواصل", "تاريخ الشكوى", "التفاصيل", "الردود",
                 "أنشئ بواسطة"]),
       actions=SC_EXPORT)

# Invoices
screen("invoices", "add_invoice", "Add Invoice", "إنشاء فاتورة", "/en/invoices/create", ("Invoices - Add", "الفواتير - إضافة"),
       filters=UNIT_SEARCH_FILTERS, actions=SEARCH_CLEAR, form="invoices.add_invoice")
screen("invoices", "end_of_day", "End Of Day", "نهاية اليوم", "/en/invoices/end-of-day", ("End of Day", "نهاية اليوم"),
       filters=(["Date *"], ["التاريخ *"]),
       columns=(["Employee", "Safe", "Payment Type", "Status", "Invoice Number", "Customer", "Unit", "Invoice Type",
                 "Amount"] + INVOICE_DATES_EN,
                ["الموظف", "الخزينة", "نوع الدفع", "الحالة", "رقم الفاتورة", "العميل", "الوحدة", "نوع الفاتورة",
                 "المبلغ"] + INVOICE_DATES_AR),
       actions=SC_COLS)
screen("invoices", "full_end_of_day", "Full End Of Day", "نهاية اليوم الكاملة", "/en/invoices/full-end-of-day",
       ("Full End of Day", "نهاية اليوم الكاملة"),
       filters=(["Date *", "Safe", "Employee"], ["التاريخ *", "الخزنة", "الموظف"]),
       sections=(["Payment Statistics per Employee"], ["إحصائيات المدفوعات لكل موظف"]),
       columns=(["Employee", "Safe", "Cash", "Visa", "Online", "Sister Company", "Cheque", "Instapay", "Total Voided",
                 "Void Requested", "Total Refunded", "Partially Refunded", "Refund Requested",
                 "Estimated Cost Refund", "Net Balance", "Payment Type", "Status", "Invoice Number", "Customer Name",
                 "Service Name", "Unit", "Invoice Type", "Amount"] + INVOICE_DATES_EN,
                ["الموظف", "الخزينة", "نقدي", "فيزا", "أونلاين", "شركة شقيقة", "شيك", "إنستاباي", "إجمالي الملغي",
                 "طلبات الإلغاء", "إجمالي المسترد", "المسترد جزئياً", "طلبات الاسترداد", "رد التكلفة التقديرية",
                 "صافي الرصيد", "نوع الدفع", "الحالة", "رقم الفاتورة", "اسم العميل", "اسم الخدمة", "الوحدة",
                 "نوع الفاتورة", "المبلغ"] + INVOICE_DATES_AR),
       actions=SC_COLS + "|Print=طباعة")
screen("invoices", "refund", "Refund", "استرداد", "/en/invoices/refund", ("Refunds - Search", "المستردات - بحث"),
       filters=(["Invoice Number", "Invoice Item Number", "Status", "ERP Reference", "ERP Refund Reference",
                 "Date From", "Date To"],
                ["رقم الفاتورة", "رقم بند الفاتورة", "الحالة", "مرجع ERP", "مرجع استرداد ERP", "من تاريخ", "إلى تاريخ"]),
       columns=(["Invoice Number", "Invoice Item Number", "Customer", "Unit", "Total Amount", "Payment Type",
                 "ERP Reference", "ERP Refund Reference", "Refund Status", "Refund Requested By", "Refunded By",
                 "Refund Request Reason", "Refund Reason", "Actions"],
                ["رقم الفاتورة", "رقم بند الفاتورة", "العميل", "الوحدة", "المبلغ الإجمالي", "نوع الدفع", "مرجع ERP",
                 "مرجع استرداد ERP", "حالة الاسترداد", "طلب الاسترداد بواسطة", "تم الاسترداد بواسطة",
                 "سبب طلب الاسترداد", "سبب الاسترداد", "الإجراءات"]),
       actions=SC_COLS + "|Refund Request=طلب استرداد|Refund=استرداد")
screen("invoices", "search_invoices", "Search Invoices", "بحث الفواتير", "/en/invoices/search",
       ("Invoices - Search", "الفواتير - بحث"),
       filters=(["Ticket ID", "Invoice Number", "Status", "Invoice Type", "Customer Filter", "Department", "Service",
                 "Collected By", "Created By", "Unit Number", "Date From", "Date To", "Request From", "Contact Channel"],
                ["رقم التذكرة", "رقم الفاتورة", "الحالة", "نوع الفاتورة", "تصفية العملاء", "القسم", "الخدمة",
                 "محصل بواسطة", "أنشئ بواسطة", "رقم الوحدة", "من تاريخ", "إلى تاريخ", "مصدر الطلب", "قناة التواصل"]),
       columns=(["Print", "Creation Date", "Created By", "Contact Channel", "Invoice Number", "Ticket ID", "Status",
                 "Notes", "Total Amount", "Payment Type", "Sister Company", "Invoice Type", "Department", "Services",
                 "Customer", "Unit", "Void Requested By", "Void Reason", "Voided By", "Invoice Collected By",
                 "Invoice Collected Date", "Request From", "EOD", "Full EOD"],
                ["طباعة", "تاريخ الإنشاء", "تم الإنشاء بواسطة", "قناة التواصل", "رقم الفاتورة", "رقم التذكرة",
                 "الحالة", "ملاحظات", "المبلغ الإجمالي", "نوع الدفع", "الشركة الشقيقة", "نوع الفاتورة", "القسم",
                 "الخدمات", "العميل", "الوحدة", "تم طلب الإلغاء بواسطة", "سبب الإلغاء", "تم الإلغاء بواسطة",
                 "تم التحصيل بواسطة", "تاريخ التحصيل", "مصدر الطلب", "نهاية اليوم", "نهاية يوم كاملة"]),
       actions=SC_EXPORT)

# Reports
screen("reports", "daily_invoices", "Daily Invoices", "الفواتير اليومية", "/en/reports/daily-invoices",
       ("Daily Invoices Report", "تقرير الفواتير اليومية"),
       filters=(["Date From *", "Date To *", "Department", "Unit Number", "Collected By", "Invoice Type"],
                ["من تاريخ *", "إلى تاريخ *", "القسم", "رقم الوحدة", "تم التحصيل بواسطة", "نوع الفاتورة"]),
       actions=SEARCH_CLEAR)
screen("reports", "department_service_eod", "Department Service End Of Day Report", "تقرير نهاية اليوم لخدمات الأقسام",
       "/en/reports/departmental-services", ("Departmental Services Report", "تقرير خدمات الأقسام"),
       filters=(["Date From *", "Date To *", "Department"], ["من تاريخ *", "إلى تاريخ *", "القسم"]), actions=SEARCH_CLEAR)
screen("reports", "end_of_day_report", "End Of Day Report", "تقرير نهاية اليوم", "/en/reports/end-of-day",
       ("End of Day Report", "تقرير نهاية اليوم"),
       filters=(["Date From *", "Date To *"], ["من تاريخ *", "إلى تاريخ *"]), actions=SEARCH_CLEAR)

# Users
screen("users", "add_legal_users", "Add Legal Users", "إضافة المستخدمين القانونيين", "/en/users/legal-users-add",
       ("Legal Employees - Add", "الموظفون القانونيون - إضافة"),
       form_fields=(["Full Name *", "Mobile Number *"], ["الاسم الكامل *", "رقم الجوال *"]), actions="Add=إضافة|Cancel=إلغاء")
screen("users", "add_user", "Add User", "إضافة مستخدم", "/en/users/add", ("Users - Add", "المستخدمون - إضافة"),
       form_fields=(["Username *", "Full Name *", "Position *", "Phone Number *", "Department *", "Employee Type *",
                     "Safe", "Manager", "Email", "Gender *", "Role *"],
                    ["اسم المستخدم *", "الاسم الكامل *", "المنصب *", "رقم الهاتف *", "القسم *", "نوع الموظف *",
                     "الخزنة", "المدير", "البريد الإلكتروني", "الجنس *", "الصلاحية *"]),
       actions="Add=إضافة|Clear=مسح")
screen("users", "manage_legal_users", "Manage Legal Users", "إدارة المستخدمين القانونيين", "/en/users/legal-users-manage",
       ("Legal Employees - Search", "الموظفون القانونيون - بحث"),
       filters=(["Full Name", "Mobile Number", "Status"], ["الاسم الكامل", "رقم الجوال", "الحالة"]),
       columns=(["Edit", "Status", "Full Name", "Mobile Number", "Project"],
                ["تعديل", "الحالة", "الاسم الكامل", "رقم الجوال", "المشروع"]),
       actions=SC_COLS)
screen("users", "manage_users", "Manage Users", "إدارة المستخدمين", "/en/users/manage", ("Users - Search", "المستخدمون - بحث"),
       filters=(["Username", "Role", "Status"], ["اسم المستخدم", "الصلاحية", "الحالة"]),
       columns=(["Edit", "Status", "Reset Password", "Username", "Full Name", "Phone Number", "Email", "Gender",
                 "Department", "Position", "Last Login"],
                ["تعديل", "الحالة", "إعادة تعيين كلمة المرور", "اسم المستخدم", "الاسم الكامل", "رقم الهاتف",
                 "البريد الإلكتروني", "الجنس", "القسم", "المنصب", "آخر تسجيل دخول"]),
       actions=SC_COLS)

# Roles
screen("roles", "add_role", "Add Role", "إضافة دور", "/en/roles/add", ("Roles - Add", "إدارة الصلاحيات - إضافة"),
       form_fields=(["Role Name (English) *", "Role Name (Arabic) *", "Module", "Permissions"],
                    ["اسم الصلاحية (إنجليزي) *", "اسم الصلاحية (عربي) *", "الوحدة", "الصلاحيات"]),
       actions="Add=إضافة|Clear=مسح")
screen("roles", "manage_roles", "Manage Roles", "إدارة الأدوار", "/en/roles/manage", ("Roles", "إدارة الصلاحيات"),
       filters=(["Search Roles"], ["البحث في الصلاحيات"]),
       columns=(["Role Name", "Actions"], ["اسم الصلاحية", "الإجراءات"]),
       actions="Add=إضافة|Export to Excel=تصدير إلى إكسل|Columns=الأعمدة")

# Document Library (single item)
screen("document_library", "search", "DocumentLibrary", "مكتبة المستندات", "/en/document-library",
       ("Document Library - Search", "مكتبة المستندات - بحث"),
       filters=(["Media Type", "Unit Number", "File Name", "Description", "Customer Name", "ID Number", "Mobile Number",
                 "Customer Code", "Ticket ID", "Invoice ID", "Complaint ID"],
                ["نوع الوسائط", "رقم الوحدة", "اسم الملف", "الوصف", "اسم العميل", "رقم الهوية", "رقم الجوال",
                 "كود العميل", "رقم التذكرة", "رقم الفاتورة", "رقم الشكوى"]),
       columns=(["Download", "View", "ID", "Unit Number", "Media Type", "File Name", "Customer Name", "Description",
                 "Created By", "Created at", "Updated at"],
                ["تحميل", "عرض", "المعرف", "رقم الوحدة", "نوع الوسائط", "اسم الملف", "اسم العميل", "الوصف",
                 "تم الإنشاء بواسطة", "تاريخ الإنشاء", "تاريخ التحديث"]),
       actions=SC_COLS, is_group_item=True)

# Settings (single item)
screen("settings", "system_configuration", "Settings", "الاعدادات", "/en/settings/search",
       ("System Configuration", "إعدادات النظام"), actions="Save=حفظ", is_group_item=True,
       note="Page showed only a heading and a Save button for this account (no visible settings fields).")

# Ownership Managment
screen("ownership", "add_request", "Add Request", "إضافة طلب", "/en/ownership-management/add",
       ("Ownership Management - Add", "إدارة الملكية - إضافة"),
       filters=UNIT_SEARCH_FILTERS_ID, actions=SEARCH_CLEAR, form="ownership.add_request")
screen("ownership", "search_request", "Search Request", "البحث عن طلب", "/en/ownership-management/search",
       ("Ownership Management - Search", "إدارة الملكية - بحث"),
       filters=(["Unit Number", "Unit ID", "Exact Match", "Category", "Status", "Created By", "Date From", "Date To"],
                ["رقم الوحدة", "معرف الوحدة", "مطابقة تامة", "الفئة", "الحالة", "أنشئ بواسطة", "من تاريخ", "إلى تاريخ"]),
       columns=(["Request ID", "Unit Number", "Category", "Description", "Status", "Attachments", "Created By",
                 "Created At", "Closed By", "Closed Date"],
                ["رقم الطلب", "رقم الوحدة", "الفئة", "الوصف", "الحالة", "المرفقات", "أنشئ بواسطة", "تاريخ الإنشاء",
                 "أغلق بواسطة", "تاريخ الإغلاق"]),
       actions=SC_COLS)

# Imports
for sid, en, ar, url, h_en, h_ar in [
    ("import_customers", "Import Customers", "استيراد العملاء", "/en/imports/customers", "Import customers", "استيراد العملاء"),
    ("import_relatives", "Import Relatives", "استيراد الأقارب", "/en/imports/relatives", "Import relatives", "استيراد الأقارب"),
    ("import_units", "Import Units", "استيراد الوحدات", "/en/imports/units", "Import units", "استيراد الوحدات"),
]:
    screen("imports", sid, en, ar, url, (h_en, h_ar), form_fields=(["Excel sheet"], ["ملف Excel"]), actions="Upload=رفع")
screen("imports", "import_history", "Import History", "سجل الاستيراد", "/en/imports/history", ("Import history", "سجل الاستيراد"),
       columns=(["ID", "Type", "File", "Status", "Inserted", "Updated", "Skipped", "Uploaded by", "Uploaded at",
                 "Rejected rows"],
                ["الرقم", "النوع", "الملف", "الحالة", "المضافة", "المحدّثة", "المتخطاة", "رفعه", "وقت الرفع",
                 "الصفوف المرفوضة"]),
       actions="Refresh=تحديث|Columns=الأعمدة")

# Notifications (single item) - link is broken on the site
screen("notifications", "send", "Notifications", "الإشعارات", "/en/notifications/send", (None, None), is_group_item=True,
       note="Sidebar item opens /en/notifications/send, which returned HTTP 404 during the crawl.")

# ---------------------------------------------------------------- detail views (opened from a result row)
DETAILS = [
    dict(
        id="unit.details", group="unit", en="Unit Details", ar="تفاصيل الوحدة", url="/en/units/{unit_id}",
        reached_from="unit.search", how=("Click a unit row in the results", None),
        sections=(["Unit Information", "Specifications"], ["معلومات الوحدة", "المواصفات"]),
        fields=(["Unit Number", "Project Name", "Unit Type", "Delivery Date", "Contracting Date", "Broker",
                 "Eligible for Rent", "Address", "Location", "Total Area", "Floor", "Rooms", "Bathrooms",
                 "Living Rooms", "Balconies", "Furnished"],
                ["رقم الوحدة", "اسم المشروع", "نوع الوحدة", "تاريخ التسليم", "تاريخ التعاقد", "وسيط", "مؤهل للإيجار",
                 "العنوان", "الموقع", "المساحة الكلية", "الطابق", "الغرف", "الحمامات", "غرف المعيشة", "الشرفات",
                 "مفروشة"]),
        tabs=[("Owners", "مالك"), ("Renters", "مستأجر"), ("Owner relatives", "قريب المالك")],
        columns=(["Customer Name", "ID Type", "ID Number", "Mobile Number", "Customer Type", "Ownership", "Owner Type",
                  "Contract Number", "Sign Date", "Country", "Actions"],
                 ["اسم العميل", "نوع الهوية", "رقم الهوية", "رقم الجوال", "نوع العميل", "الملكية", "نوع المالك",
                  "رقم العقد", "تاريخ التوقيع", "الدولة", "الإجراءات"]),
        panels=[("Show Invoices", "عرض الفواتير", "Invoices", "الفواتير"),
                ("Show Tickets", "عرض التذاكر", "Tickets", "التذاكر"),
                ("Ownership History", "سجل الملكية", "Past Owners", "الملاك السابقون"),
                ("EGP Show Debt", "EGP عرض المديونية", "Unit Debt / Unsettled Payments", "مديونية الوحدة / المدفوعات غير المسواة"),
                ("Show Documents", "عرض المستندات", "Documents", "المستندات")],
        actions="Create Ticket=إنشاء تذكرة|Upload Document=رفع مستند|Assign Location=تعيين الموقع|Disable Rent=إلغاء الإيجار|Edit ownership=تعديل الملكية|End ownership=إنهاء الملكية|Columns=الأعمدة",
        opens={"Create Ticket": "tickets.add_ticket"},
    ),
    dict(
        id="customers.details", group="customers", en="Customer Details", ar=None, url="/en/customers/{customer_id}",
        reached_from="customers.search_customer", how=("Click a customer row in the results", None),
        sections=(["Personal Information", "Contact Information", "Emergency Contact", "Notes", "Units", "Cars"],
                  ["المعلومات الشخصية", "معلومات الاتصال", "جهة الاتصال الطارئ", "ملاحظات", "الوحدات", "السيارات"]),
        columns=(UNIT_COLS_EN + ["Delivery Date", "Make", "Model", "Plate Text", "Plate Number"],
                 UNIT_COLS_AR + ["تاريخ التسليم", "الشركة المصنعة", "الموديل", "نص اللوحة", "رقم اللوحة"]),
        actions="Edit Customer=تعديل العميل|Show Documents=عرض المستندات|Upload Document=رفع مستند|Add Ticket=إضافة تذكرة|Columns=الأعمدة",
    ),
]


# ---------------------------------------------------------------- builders
def pairs(spec):
    """(en_list, ar_list|None) -> [{'en','ar','required'}]"""
    if not spec:
        return []
    en, ar = spec
    if ar is not None and len(ar) != len(en):
        raise ValueError(f"EN/AR length mismatch: {en} / {ar}")
    out = []
    for i, e in enumerate(en):
        a = ar[i] if ar else None
        req = e.endswith(" *")
        out.append({"en": e.removesuffix(" *"), "ar": a.removesuffix(" *") if a else None, "required": req})
    return out


def names(items, lang):
    return [x[lang] for x in items if x.get(lang)]


def text_block(doc, lang):
    L = lambda d: (d or {}).get(lang) or ""
    lines = [
        f"{'Screen' if lang == 'en' else 'الشاشة'}: {L(doc['screen'])}",
        f"{'Group' if lang == 'en' else 'المجموعة'}: {L(doc['group'])}",
        f"{'Navigation path' if lang == 'en' else 'مسار التنقل'}: {L(doc['path'])}",
    ]
    if L(doc.get("page_title")):
        lines.append(f"{'Page title' if lang == 'en' else 'عنوان الصفحة'}: {L(doc['page_title'])}")
    for key, en_lbl, ar_lbl in [("tabs", "Tabs", "التبويبات"), ("sections", "Sections", "الأقسام"),
                                ("filters", "Search filters", "حقول البحث"), ("form_fields", "Form fields", "حقول النموذج"),
                                ("fields", "Fields", "الحقول"),
                                ("columns", "Table columns", "أعمدة الجدول"), ("actions", "Actions", "الإجراءات")]:
        vals = names(doc.get(key) or [], lang)
        if vals:
            lines.append(f"{en_lbl if lang == 'en' else ar_lbl}: {', '.join(vals)}")
    steps = [s[lang] for s in doc.get("navigation_steps", []) if s.get(lang)]
    if steps:
        lines.append(("How to get there: " if lang == "en" else "طريقة الوصول: ") + " → ".join(steps))
    return "\n".join(lines)


def finish(doc):
    doc["text_en"] = text_block(doc, "en")
    doc["text_ar"] = text_block(doc, "ar")
    return doc


def lab(en, ar):
    return {"en": en, "ar": ar}


docs = []
by_id = {}

# group documents
for key, en, ar in GROUPS:
    items = [s for s in S if s["group"] == key]
    single = len(items) == 1 and items[0].get("is_group_item")
    d = finish({
        "id": f"group.{key}", "type": "group", "group": GROUP[key], "screen": GROUP[key],
        "path": GROUP[key], "url": BASE_URL + items[0]["url"] if single else None,
        "screens": [lab(s["en"], s["ar"]) for s in items] if not single else [],
        "navigation_steps": [lab(f"Open '{en}' in the sidebar", f"افتح '{ar}' من القائمة الجانبية")],
    })
    if not single:
        d["text_en"] += "\nScreens: " + ", ".join(s["en"] for s in items)
        d["text_ar"] += "\nالشاشات: " + ", ".join(s["ar"] for s in items)
    docs.append(d)

# screen documents (+ tab docs + form docs)
for s in S:
    g = GROUP[s["group"]]
    single = s.get("is_group_item")
    path = lab(g["en"] if single else f"{g['en']} > {s['en']}", g["ar"] if single else f"{g['ar']} > {s['ar']}")
    steps = [lab(f"Open '{g['en']}' in the sidebar", f"افتح '{g['ar']}' من القائمة الجانبية")]
    if not single:
        steps.append(lab(f"Click '{s['en']}'", f"اضغط على '{s['ar']}'"))
    tabs = [lab(e, a) for e, a in s["tabs"]]
    d = {
        "id": f"screen.{s['id']}", "type": "screen", "group": g, "screen": lab(s["en"], s["ar"]),
        "path": path, "url": BASE_URL + s["url"],
        "page_title": lab(*s["title"]) if s["title"][0] else None,
        "tabs": tabs,
        "sections": [lab(e, a) for e, a in zip(*s["sections"])] if s.get("sections") else [],
        "filters": pairs(s.get("filters")),
        "form_fields": pairs(s.get("form_fields")),
        "columns": pairs(s.get("columns")),
        "actions": A(s["actions"]),
        "navigation_steps": steps,
    }
    if s.get("form"):
        d["next_step"] = f"form.{s['form']}"
        d["navigation_steps"] = steps + [lab("Search for the unit by Unit Number, then click the unit in the results",
                                             "ابحث عن الوحدة برقم الوحدة ثم اضغط على الوحدة في النتائج")]
    if s.get("row_opens"):
        d["row_opens"] = f"detail.{s['row_opens']}"
    if s.get("note"):
        d["note"] = s["note"]
    docs.append(finish(d))
    by_id[d["id"]] = d

    # one doc per tab (so a query like "legal blocks" lands on the exact tab)
    for t in tabs:
        td = (s.get("tab_details") or {}).get(t["en"], {})
        tdoc = {
            "id": f"tab.{s['id']}.{t['en'].lower().replace(' ', '_')}", "type": "tab", "parent": d["id"],
            "group": g, "screen": lab(f"{s['en']} - {t['en']}", f"{s['ar']} - {t['ar']}"),
            "tab": t,
            "path": lab(f"{path['en']} > {t['en']}", f"{path['ar']} > {t['ar']}"),
            "url": BASE_URL + s["url"],
            "filters": pairs((td["filters"], None)) if td.get("filters") else d["filters"],
            "columns": pairs((td["columns"], None)) if td.get("columns") else d["columns"],
            "navigation_steps": steps + [lab(f"Select the '{t['en']}' tab", f"اختر تبويب '{t['ar']}'")],
        }
        docs.append(finish(tdoc))

    if s.get("form"):
        f = FORMS[s["form"]]
        via = f.get("via")
        fsteps = steps + [lab("Enter the Unit Number and click 'Search'", "أدخل رقم الوحدة واضغط 'بحث'")]
        fsteps.append(lab(f"Click '{via[0]}' on the unit row", None) if via else
                      lab("Click the unit row in the results", "اضغط على صف الوحدة في النتائج"))
        fdoc = {
            "id": f"form.{s['form']}", "type": "form", "parent": d["id"], "group": g,
            "screen": lab(f"{s['en']} - {f['title'][0]}", f"{s['ar']} - {f['title'][1]}"),
            "page_title": lab(*f["title"]),
            "path": lab(f"{path['en']} > {f['title'][0]}", f"{path['ar']} > {f['title'][1]}"),
            "url": BASE_URL + f["url"],
            "tabs": [lab(e, a) for e, a in f.get("tabs", [])],
            "unit_search_results_columns": pairs(f["result_cols"]),
            "form_fields": pairs(f["fields"]),
            "actions": A(f["actions"]),
            "navigation_steps": fsteps,
        }
        if f.get("result_actions"):
            fdoc["unit_search_results_actions"] = A(f["result_actions"])
        docs.append(finish(fdoc))

# detail views
for dv in DETAILS:
    g = GROUP[dv["group"]]
    parent = by_id[f"screen.{dv['reached_from']}"]
    d = {
        "id": f"detail.{dv['id']}", "type": "detail_view", "parent": parent["id"], "group": g,
        "screen": lab(dv["en"], dv["ar"]),
        "path": lab(f"{parent['path']['en']} > {dv['en']}",
                    f"{parent['path']['ar']} > {dv['ar']}" if dv["ar"] else None),
        "url": BASE_URL + dv["url"],
        "tabs": [lab(e, a) for e, a in dv.get("tabs", [])],
        "sections": [lab(e, a) for e, a in zip(*dv["sections"])],
        "fields": pairs(dv.get("fields")),
        "columns": pairs(dv.get("columns")),
        "panels": [{"button": lab(b_en, b_ar), "shows": lab(s_en, s_ar)} for b_en, b_ar, s_en, s_ar in dv.get("panels", [])],
        "actions": A(dv["actions"]),
        "navigation_steps": parent["navigation_steps"] + [lab(*dv["how"])],
    }
    if dv.get("opens"):
        d["opens"] = {k: f"form.{v}" for k, v in dv["opens"].items()}
    finish(d)
    if d["panels"]:
        d["text_en"] += "\nView panels: " + ", ".join(f"{p['button']['en']} → {p['shows']['en']}" for p in d["panels"])
        d["text_ar"] += "\nلوحات العرض: " + ", ".join(f"{p['button']['ar']} → {p['shows']['ar']}" for p in d["panels"])
    docs.append(d)

# ---------------------------------------------------------------- Arabic gap fill (crawl-backed)
# Some labels were captured in English only. When the *same* English label was captured with
# Arabic elsewhere in this crawl, that Arabic is reused. Each entry names where it was read, and
# every filled label is tagged {"ar_source": "crawl:<where>"} in the output so it can be traced.
# Labels with no Arabic anywhere in the crawl (or with conflicting Arabic, e.g. "ID") are NOT
# listed here; they stay null until read from the Arabic UI.
AR_FROM_CRAWL = {
    "Unit Number": ("رقم الوحدة", "screen.unit.search.columns"),
    "Unit ID": ("رقم الوحدة التعريفي", "screen.unit_blocks.search_block.filters"),
    "Exact Match": ("مطابقة تامة", "screen.unit_blocks.search_block.filters"),
    "Customer Name": ("اسم العميل", "screen.unit_blocks.search_block.columns"),
    "Customer Mobile": ("جوال العميل", "screen.tickets.search_cts.columns"),
    "Project": ("المشروع", "screen.unit.search.filters"),
    "Project Name": ("اسم المشروع", "screen.unit_blocks.search_block.columns"),
    "Sub Project Code": ("كود المشروع الفرعي", "screen.unit.search.columns"),
    "Reason": ("السبب", "form.unit_blocks.add_block.form_fields"),
    "Blocked By": ("تم الحظر بواسطة", "screen.unit_blocks.search_block.columns"),
    "Status": ("الحالة", "screen.unit_blocks.search_block.columns"),
    "Category": ("الفئة", "screen.ownership.search_request.filters"),
}


# Read from the live Arabic UI on 2026-11-12 (second pass, Claude desktop + browser, read only).
# Tagged {"ar_source": "ui:<page> | <where on the page>"}.
AR_FROM_UI = {
    "ID": ("المعرف", "/ar/unit-blocks/search | Finance + Legal tabs, column header"),
    "History": ("السجل", "/ar/unit-blocks/search | Finance + Legal tabs, column header"),
    "Blocked Date": ("تاريخ الحظر", "/ar/unit-blocks/search | Finance + Legal tabs, column header"),
    "Unblocked By": ("تم إلغاء الحظر بواسطة", "/ar/unit-blocks/search | Finance + Legal tabs, column header"),
    "Unblocked Date": ("تاريخ إلغاء الحظر", "/ar/unit-blocks/search | Finance + Legal tabs, column header"),
    "From Date": ("من تاريخ", "/ar/unit-blocks/search | Finance + Legal tabs, date filter"),
    "To Date": ("إلى تاريخ", "/ar/unit-blocks/search | Finance + Legal tabs, date filter"),
    "Assigned Lawyer": ("المحامي المسؤول", "/ar/unit-blocks/search | Legal tab, filter label"),
    "Search by name...": ("البحث بالاسم...",
                          "/ar/definitions/* (erp-codes, department, invoice-types, location, location-type, "
                          "positions, rental-companies, sister-companies, unit-block-categories) | search placeholder"),
    "Search by code...": ("البحث بالكود...", "/ar/definitions/erp-codes | search placeholder"),
    # Radio groups: on screen the title is the label and the options read "نعم / لا".
    # The English crawl wrote title + options as "Active (Yes/No)", so Arabic mirrors that form.
    "Active (Yes/No)": ("نشط (نعم / لا)", "/ar/services/search | radio filter title 'نشط', options 'نعم / لا'"),
    "Show in mobile (Yes/No)": ("إظهار في التطبيق (نعم / لا)",
                                "/ar/services/search + /ar/services/add | radio title 'إظهار في التطبيق', "
                                "options 'نعم / لا'"),
    "Add Reservation": ("إضافة حجز", "/ar/rentals/add | unit result row action button"),
    "View Rental History": ("عرض سجل الإيجار", "/ar/rentals/add | unit result row action button"),
}

# Not on-screen text: names and click instructions the crawl wrote itself (their English is not
# a UI label either). Built from UI labels above / in the crawl plus the crawl's own Arabic
# sentence patterns. Tagged {"ar_source": "composed:<how>"}.
AR_COMPOSED = {
    "Customer Details": ("تفاصيل العميل",
                         "the details page has no title (H1 = customer's name); pattern of 'تفاصيل الوحدة' "
                         "+ 'العميل' as in 'اسم العميل'"),
    "Customers > Search Customer > Customer Details": ("العملاء > بحث عميل > تفاصيل العميل",
                                                       "parent path 'العملاء > بحث عميل' + 'تفاصيل العميل'"),
    "Click a unit row in the results": ("اضغط على صف الوحدة في النتائج",
                                        "same sentence the crawl uses for 'Click the unit row in the results'"),
    "Click a customer row in the results": ("اضغط على صف العميل في النتائج",
                                            "unit-row sentence pattern with 'العميل'"),
    "Click 'Add Reservation' on the unit row": ("اضغط على 'إضافة حجز' في صف الوحدة",
                                                "pattern 'اضغط على ...' + UI label 'إضافة حجز'"),
}

AR_TABLES = [("crawl", AR_FROM_CRAWL), ("ui", AR_FROM_UI), ("composed", AR_COMPOSED)]
_overlap = [k for i, (_, a) in enumerate(AR_TABLES) for _, b in AR_TABLES[i + 1:] for k in a if k in b]
assert not _overlap, f"label in more than one fill table: {_overlap}"


def fill_ar(obj, counts):
    """Fill missing Arabic in place from the tables above, tagging each label with its source."""
    if isinstance(obj, dict):
        if obj.get("en") and "ar" in obj and not obj["ar"]:
            for kind, table in AR_TABLES:
                if obj["en"] in table:
                    ar, where = table[obj["en"]]
                    obj["ar"], obj["ar_source"] = ar, f"{kind}:{where}"
                    counts[kind] += 1
                    break
        for k, v in obj.items():
            if k not in ("text_en", "text_ar"):
                fill_ar(v, counts)
    elif isinstance(obj, list):
        for v in obj:
            fill_ar(v, counts)


# Tab docs share label objects with their parent screen, so capture every doc's extra text
# (lines appended after finish(): screens, panels) BEFORE filling anything, then rebuild all.
extra_ar = {}
for d in docs:
    base_ar = text_block(d, "ar")
    assert d["text_ar"].startswith(base_ar), d["id"]
    extra_ar[d["id"]] = d["text_ar"][len(base_ar):]
filled = {kind: 0 for kind, _ in AR_TABLES}
for d in docs:
    fill_ar(d, filled)
for d in docs:
    d["text_ar"] = text_block(d, "ar") + extra_ar[d["id"]]

# ---------------------------------------------------------------- write
meta = {
    "source": BASE_URL, "product": "Ability CRM", "crawled_at": "2026-11-12",
    "crawled_as": "Super Admin (SODIC) - other users may see fewer groups/screens",
    "languages": ["en", "ar"], "doc_count": len(docs),
    "counts": {t: sum(d["type"] == t for d in docs) for t in ("group", "screen", "tab", "form", "detail_view")},
    "embedding_fields": ["text_en", "text_ar"],
    "ar_filled": filled,  # {"crawl": n, "ui": n, "composed": n}, see ar_source on each label
}
(OUT / "ability_crm_vector_docs.json").write_text(
    json.dumps({"meta": meta, "documents": docs}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(meta, ensure_ascii=False, indent=2))
