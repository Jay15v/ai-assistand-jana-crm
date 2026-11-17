# DRAFT — User Manual Additions for 12 CRM Screens

**Status:** Draft for business review · **Date:** 17 Nov 2026 · **Not yet part of the official manual**

> **Why this document exists**
>
> The CRM chatbot answers employees' "how do I…?" questions only from the official user manual. Twelve screens have no section in the manual yet, so the chatbot currently replies *"I don't have step-by-step instructions for this screen yet."* for them. This document drafts those sections.
>
> **How the drafts were written**
>
> From what the system shows on each screen (field names, filters, table columns, buttons) and from each screen's permission list. Nobody has yet *used* these screens to confirm what happens after each click, so every question ends with a **To verify** list.
>
> **What we need from the reviewer**
>
> 1. Open each screen in the real CRM and follow the steps.
> 2. Correct anything wrong directly in the text (wording, order, button names).
> 3. Answer each **To verify** item (e.g. the exact success message).
> 4. Mark the section **Approved**. Approved text is then added to the official manual (English and Arabic) and the chatbot starts answering it.
>
> **Not included:** the **Notifications** screen (not implemented yet).

**Screens covered**

| # | Screen | Goes into the manual as |
|---|---|---|
| 1 | Unit Blocks → Add Block | New section: **Unit Blocks** |
| 2 | Unit Blocks → Search Block | New section: **Unit Blocks** |
| 3 | Ownership Management → Add Request | New section: **Ownership Management** |
| 4 | Ownership Management → Search Request | New section: **Ownership Management** |
| 5 | Imports → Import Customers | New section: **Imports** |
| 6 | Imports → Import Relatives | New section: **Imports** |
| 7 | Imports → Import Units | New section: **Imports** |
| 8 | Imports → Import History | New section: **Imports** |
| 9 | Customers → Relative Requests | Added to existing section **8. Customers** |
| 10 | Invoices → Refund | Added to existing section **12. Invoices** |
| 11 | Users → Add Legal Users | Added to existing section **15. Users** |
| 12 | Users → Manage Legal Users | Added to existing section **15. Users** |

---

# Part 1 — English

## Unit Blocks *(new section)*

**Purpose:** lock a unit for **finance** or **legal** reasons so it is flagged across the system, and lift the lock when the issue is resolved.
**Menu:** **Unit Blocks → Add Block / Search Block**.

### How do I block a unit (finance or legal block)?

**Keywords:** block unit, lock unit, finance block, legal block, stop unit

1. Go to **Unit Blocks → Add Block**. The page is titled **Block Unit**.
2. Enter the **Unit Number** (or **Unit ID**). Tick **Exact Match** to match the number exactly. Click **Search**.
3. Click the unit row in the results. The **Unit Blocks - Block Details** page opens and shows **Unit Number**, **Project Name**, **Unit Type**, **Customer Name** and **Mobile Number**.
4. Choose the tab for the block type: **Finance** or **Legal**.
5. Enter the **Reason**. Optionally add **Attachments** (**Show Attachments** lists files already attached).
6. Click **Block Unit** (or **Cancel**).

Locked units then appear in **Unit → Search** with the **Locked** filter (see section 9).

**To verify**

- [ ] Does the **Legal** tab ask for more fields than the **Finance** tab (e.g. **Category**, **Assigned Lawyer**)? The Legal search screen filters by both.
- [ ] Is a user without the **Legal Block** permission shown only the **Finance** tab (and vice versa)?
- [ ] Exact success message after **Block Unit**.
- [ ] What does **Save Changes** do on this page, compared with **Block Unit**?
- [ ] Can a unit carry a Finance and a Legal block at the same time?

---

### How do I find blocked units?

**Keywords:** search block, blocked units, block list, legal blocks, finance blocks

1. Go to **Unit Blocks → Search Block**.
2. Choose a tab:
    - **All**: every unit with its block flags. Filters: **Unit Number**, **Unit ID**, **Block Type**, **Exact Match**.
    - **Finance**: finance blocks. Filters: **Unit Number**, **Unit ID**, **Project**, **Customer Name**, **Customer Mobile**, **From Date**, **To Date**, **Exact Match**.
    - **Legal**: legal blocks. Same filters as Finance plus **Category** and **Assigned Lawyer**.
3. Click **Search**. Use **Clear** to reset and **Columns** to show or hide columns.

| Tab | Main columns |
|---|---|
| All | Unit Number, Blocked, Legal Block, Finance Block, Project Name, Unit Type, Blocked By, Customer Name, Mobile Number, Sign Date |
| Finance | ID, Unit Number, History, Project Name, Reason, Blocked By, Blocked Date, Unblocked By, Unblocked Date, Status |
| Legal | ID, Unit Number, History, Project Name, Category, Reason, Blocked By, Blocked Date, Unblocked By, Unblocked Date, Status |

**To verify**

- [ ] Values of the **Block Type** filter and of the **Status** column.
- [ ] What the **History** column opens.

---

### How do I unblock a unit?

**Keywords:** unblock unit, lift block, remove block, release unit

1. Go to **Unit Blocks → Search Block** and open the **Finance** or **Legal** tab.
2. Search for the unit and find its active block row.
3. Use the row's **UnBlock** action and confirm.
4. The row then shows **Unblocked By** and **Unblocked Date**; the unit is no longer locked.

**To verify**

- [ ] Where exactly the **UnBlock** action is (row icon, button, or inside the block details) and its exact label.
- [ ] Does unblocking ask for a reason or a confirmation? Exact messages.
- [ ] Is unblocking allowed only to users with the **UnBlock** permission?

---

## Ownership Management *(new section)*

**Purpose:** record and follow up ownership requests on a unit, each with a category, a description and attachments, until it is closed. The time allowed is the **Ownership Management SLA** in **Settings**.
**Menu:** **Ownership Management → Add Request / Search Request**.

### How do I add an ownership request?

**Keywords:** ownership request, new ownership request, ownership transfer, unit ownership

1. Go to **Ownership Management → Add Request**.
2. Enter the **Unit Number** (or **Unit ID**), tick **Exact Match** if needed, and click **Search**.
3. Click the unit row. The **New Ownership Management Request** form opens.
4. Choose the **Category**, write the **Description**, and optionally add **Attachments**.
5. Click **Add** (or **Cancel**).

**To verify**

- [ ] List of **Category** values.
- [ ] Which fields are required.
- [ ] Exact success message and the page shown after **Add**.

---

### How do I find, close or invalidate an ownership request?

**Keywords:** search ownership request, close ownership request, invalid request, ownership status

1. Go to **Ownership Management → Search Request**.
2. Filter by **Unit Number**, **Unit ID** (with **Exact Match**), **Category**, **Status**, **Created By**, **Date From**, **Date To**. Click **Search**.
3. The results show **Request ID**, **Unit Number**, **Category**, **Description**, **Status**, **Attachments**, **Created By**, **Created At**, **Closed By**, **Closed Date**.
4. To finish a request, use **Close Ownership Request**. To reject a wrong or duplicate request, mark it **Invalid**. **Closed By** and **Closed Date** are filled in.

**To verify**

- [ ] Where the **Close** and **Invalid** actions are, and their exact labels.
- [ ] Values of the **Status** filter.
- [ ] Can a request be edited, and which fields?
- [ ] Is the SLA shown on the request (e.g. a delay sign like tickets)?

---

## Imports *(new section)*

**Purpose:** add or update many customers, owner relatives or units at once from an Excel file, and check each import's result.
**Menu:** **Imports → Import Customers / Import Relatives / Import Units / Import History**.

### How do I import customers, relatives or units from Excel?

**Keywords:** import excel, bulk upload, import customers, import relatives, import units, upload sheet

1. Go to **Imports** and choose **Import Customers**, **Import Relatives** or **Import Units**.
2. Choose the **Excel sheet** file.
3. Click **Upload**.
4. Check the result in **Imports → Import History** (next question).

**To verify**

- [ ] The required columns of each Excel file (one table per import type), and whether a template can be downloaded.
- [ ] Required file name or format (e.g. `.xlsx` only), and the size or row limit.
- [ ] Does an import **update** existing records or only add new ones? How are existing records matched (ID number, unit number…)?
- [ ] Message shown after **Upload**.

---

### How do I check the result of an import?

**Keywords:** import history, import result, rejected rows, failed import

1. Go to **Imports → Import History**.
2. Each import shows **ID**, **Type**, **File**, **Status**, **Inserted**, **Updated**, **Skipped**, **Uploaded by**, **Uploaded at** and **Rejected rows**.
3. Click **Refresh** to update the status of an import still running.

**To verify**

- [ ] Values of **Status**.
- [ ] What **Rejected rows** shows: a count, a downloadable file, or a list with the reason per row?
- [ ] Can the uploaded **File** be downloaded again?

---

## To add to section 8. Customers

### How do I review a relative request (accept or reject)?

**Keywords:** relative request, owner relative, accept relative, reject relative, family member

1. Go to **Customers → Relative Requests**.
2. Filter by **Request #**, **Owner ID**, **Unit Number**, **Owner Phone Number**, **Relative ID Number**, **Project**, **Status**. Click **Search**.
3. Review the request: **Owner Name**, **Owner Code**, **Unit Number**, **Relative Name**, **Relation**, **ID Type**, **Relative ID #**, **Phone**, **Email**. Click **Show Media** to see the attached documents.
4. Click **Accept** or **Reject**.
5. **Cancel** removes a request that was already accepted (permission **Delete Accept Request**).

**Export to Excel** and **Columns** work as on other search pages.

**To verify**

- [ ] Where the requests come from (e.g. owners adding relatives in the MyPorto app).
- [ ] Does **Reject** ask for a reason? Exact messages after Accept / Reject.
- [ ] After **Accept**, does the relative appear as **Owner Relative** in the customer's page?
- [ ] Exact meaning of **Cancel** (assumed: undo an accepted request).

---

## To add to section 12. Invoices

### How do I review refund requests?

**Keywords:** refund, refund request, approve refund, reject refund, money back

1. Go to **Invoices → Refund**.
2. Filter by **Invoice Number**, **Invoice Item Number**, **Status**, **ERP Reference**, **ERP Refund Reference**, **Date From**, **Date To**. Click **Search**.
3. Each row shows **Invoice Number**, **Invoice Item Number**, **Customer**, **Unit**, **Total Amount**, **Payment Type**, **ERP Reference**, **ERP Refund Reference**, **Refund Status**, **Refund Requested By**, **Refunded By**, **Refund Request Reason** and **Refund Reason**.
4. Use the row actions to approve (**Refund**) or reject the request.

The related invoice statuses are **Refund Requested**, **Refunded** and **Partially Refund** (see the invoice statuses at the start of this section).

**To verify**

- [ ] Where a refund is first requested: from the invoice details (**Search Invoices**) or from this page (**Refund Request** button)?
- [ ] Exact labels of the approve and reject actions, and whether a **Refund Reason** must be typed.
- [ ] How a partial refund is made (per **Invoice Item**?).
- [ ] Does an approved refund change the cashier's **End Of Day** totals (Total Refunded)?

---

## To add to section 15. Users

### How do I add a legal user?

**Keywords:** legal user, add lawyer, legal employee

1. Go to **Users → Add Legal Users**. The page is titled **Legal Employees - Add**.
2. Enter **Full Name** and **Mobile Number**.
3. Click **Add** (or **Cancel**).

**To verify**

- [ ] What a legal user is used for (assumed: the lawyers selectable as **Assigned Lawyer** on legal unit blocks).
- [ ] Does a legal user get a CRM login, or is it a contact record only?
- [ ] Exact success message; is the **Project** set automatically?

---

### How do I find or edit legal users?

**Keywords:** manage legal users, edit lawyer, deactivate legal user

1. Go to **Users → Manage Legal Users** (**Legal Employees - Search**).
2. Filter by **Full Name**, **Mobile Number**, **Status**. Click **Search**.
3. The results show **Status**, **Full Name**, **Mobile Number** and **Project**. Click **Edit** in the row to change the user.

**To verify**

- [ ] Which fields can be edited, and how a legal user is deactivated (the **Status** column).

---

# Part 2 — العربي

<div dir="rtl" markdown="1">

## حظر الوحدات *(قسم جديد)*

**الغرض:** قفل وحدة لأسباب **مالية** أو **قانونية** عشان تبان مقفولة في النظام كله، وفك القفل لما المشكلة تتحل.
**القائمة:** **حظر الوحدات** ← **إضافة حظر** / **بحث عن حظر**.

### إزاي أحظر وحدة (حظر مالي أو قانوني)؟

1. ادخل **حظر الوحدات** ← **إضافة حظر**. عنوان الصفحة **Block Unit**.
2. اكتب **رقم الوحدة** (أو **Unit ID**). علّم **Exact Match** لو عايز الرقم بالظبط. اضغط **بحث**.
3. اضغط على صف الوحدة في النتايج. هتفتح صفحة **Unit Blocks - Block Details** وفيها رقم الوحدة، اسم المشروع، نوع الوحدة، اسم العميل، ورقم الموبايل.
4. اختار التاب حسب نوع الحظر: **Finance** (مالي) أو **Legal** (قانوني).
5. اكتب **السبب**، واختياري ترفع **مرفقات** (**Show Attachments** بيعرض الملفات المرفوعة قبل كده).
6. اضغط **Block Unit** (أو **Cancel**).

الوحدات المقفولة بتظهر بعد كده في **الوحدة** ← البحث بفلتر **مقفولة** (قسم 9).

**محتاج تأكيد**

- [ ] هل تاب **Legal** بيطلب حقول زيادة عن **Finance** (زي **Category** و **Assigned Lawyer**)؟ شاشة البحث القانوني بتفلتر بيهم.
- [ ] هل المستخدم اللي معاهوش صلاحية **Legal Block** بيشوف تاب **Finance** بس (والعكس)؟
- [ ] رسالة النجاح بالظبط بعد **Block Unit**.
- [ ] زرار **Save Changes** بيعمل إيه مقارنة بـ **Block Unit**؟
- [ ] ينفع الوحدة يبقى عليها حظر مالي وقانوني في نفس الوقت؟

---

### إزاي ألاقي الوحدات المحظورة؟

1. ادخل **حظر الوحدات** ← **بحث عن حظر**.
2. اختار التاب:
    - **All**: كل الوحدات وعلامات الحظر بتاعتها. الفلاتر: رقم الوحدة، Unit ID، نوع الحظر، Exact Match.
    - **Finance**: الحظر المالي. الفلاتر: رقم الوحدة، Unit ID، المشروع، اسم العميل، موبايل العميل، من تاريخ، إلى تاريخ، Exact Match.
    - **Legal**: الحظر القانوني. نفس فلاتر المالي وزيادة **Category** و **Assigned Lawyer**.
3. اضغط **بحث**. **مسح** بيرجّع الفلاتر، و**الأعمدة** بتظهر أو تخفي أعمدة.

**محتاج تأكيد**

- [ ] قيم فلتر **Block Type** وعمود **Status**.
- [ ] عمود **History** بيفتح إيه.

---

### إزاي أفك الحظر عن وحدة؟

1. ادخل **حظر الوحدات** ← **بحث عن حظر** وافتح تاب **Finance** أو **Legal**.
2. دوّر على الوحدة ولاقي صف الحظر الشغال.
3. استخدم إجراء **UnBlock** في الصف وأكّد.
4. الصف هيظهر فيه **Unblocked By** و **Unblocked Date**، والوحدة مش هتبقى مقفولة.

**محتاج تأكيد**

- [ ] مكان إجراء **UnBlock** بالظبط (أيقونة في الصف، زرار، ولا جوه تفاصيل الحظر) واسمه.
- [ ] هل فك الحظر بيطلب سبب أو تأكيد؟ الرسايل بالظبط.
- [ ] هل فك الحظر مسموح بس لصاحب صلاحية **UnBlock**؟

---

## إدارة الملكية *(قسم جديد)*

**الغرض:** تسجيل ومتابعة طلبات الملكية على الوحدة، كل طلب بتصنيف ووصف ومرفقات، لحد ما يتقفل. الوقت المسموح هو **Ownership Management SLA** في **الإعدادات**.
**القائمة:** **إدارة الملكية** ← **إضافة طلب** / **البحث عن طلب**.

### إزاي أضيف طلب ملكية؟

1. ادخل **إدارة الملكية** ← **إضافة طلب**.
2. اكتب **رقم الوحدة** (أو **Unit ID**)، وعلّم **Exact Match** لو محتاج، واضغط **بحث**.
3. اضغط على صف الوحدة. هتفتح فورم **New Ownership Management Request**.
4. اختار **Category**، واكتب **Description**، واختياري ارفع **Attachments**.
5. اضغط **Add** (أو **Cancel**).

**محتاج تأكيد**

- [ ] قيم **Category**.
- [ ] الحقول الإجبارية.
- [ ] رسالة النجاح والصفحة اللي بتظهر بعد **Add**.

---

### إزاي ألاقي طلب ملكية أو أقفله أو ألغيه؟

1. ادخل **إدارة الملكية** ← **البحث عن طلب**.
2. فلتر بـ رقم الوحدة، Unit ID (مع Exact Match)، Category، Status، Created By، من تاريخ، إلى تاريخ. اضغط **بحث**.
3. النتايج فيها رقم الطلب، رقم الوحدة، Category، الوصف، الحالة، المرفقات، Created By، تاريخ الإنشاء، Closed By، تاريخ القفل.
4. لإنهاء الطلب استخدم **Close Ownership Request**. ولرفض طلب غلط أو متكرر علّمه **Invalid**. هيتسجل **Closed By** و **Closed Date**.

**محتاج تأكيد**

- [ ] مكان إجراءات **Close** و **Invalid** وأسماءهم بالظبط.
- [ ] قيم فلتر **Status**.
- [ ] ينفع نعدّل الطلب؟ وأنهي حقول؟
- [ ] هل الـ SLA بيظهر على الطلب (علامة تأخير زي التذاكر)؟

---

## الاستيراد *(قسم جديد)*

**الغرض:** إضافة أو تحديث عملاء أو أقارب ملاك أو وحدات كتير مرة واحدة من ملف إكسل، ومتابعة نتيجة كل استيراد.
**القائمة:** **الاستيراد** ← **استيراد العملاء** / **استيراد الأقارب** / **استيراد الوحدات** / **سجل الاستيراد**.

### إزاي أستورد عملاء أو أقارب أو وحدات من إكسل؟

1. ادخل **الاستيراد** واختار **استيراد العملاء** أو **استيراد الأقارب** أو **استيراد الوحدات**.
2. اختار ملف **Excel sheet**.
3. اضغط **Upload**.
4. تابع النتيجة في **الاستيراد** ← **سجل الاستيراد** (السؤال الجاي).

**محتاج تأكيد**

- [ ] الأعمدة المطلوبة في ملف كل نوع (جدول لكل نوع)، وهل فيه تمبلت ينفع يتنزّل.
- [ ] اسم أو نوع الملف المطلوب (`.xlsx` بس؟)، وأقصى حجم أو عدد صفوف.
- [ ] الاستيراد بيحدّث البيانات الموجودة ولا بيضيف جديد بس؟ وبيتعرف على الموجود بإيه (رقم البطاقة، رقم الوحدة…)؟
- [ ] الرسالة اللي بتظهر بعد **Upload**.

---

### إزاي أتابع نتيجة الاستيراد؟

1. ادخل **الاستيراد** ← **سجل الاستيراد**.
2. كل استيراد بيظهر فيه ID، النوع، الملف، الحالة، Inserted، Updated، Skipped، رفعه مين، اترفع إمتى، و**Rejected rows**.
3. اضغط **Refresh** عشان تحدّث حالة استيراد لسه شغال.

**محتاج تأكيد**

- [ ] قيم **Status**.
- [ ] **Rejected rows** بيعرض إيه: عدد، ملف ينزل، ولا قايمة بسبب كل صف؟
- [ ] ينفع ننزّل الملف المرفوع تاني؟

---

## يتضاف لقسم 8. العملاء

### إزاي أراجع طلب قريب (قبول أو رفض)؟

1. ادخل **العملاء** ← **صلة القرابة**.
2. فلتر بـ رقم الطلب، Owner ID، رقم الوحدة، موبايل المالك، رقم بطاقة القريب، المشروع، الحالة. اضغط **بحث**.
3. راجع الطلب: اسم المالك، كود المالك، رقم الوحدة، اسم القريب، صلة القرابة، نوع الهوية، رقم هوية القريب، الموبايل، الإيميل. اضغط **Show Media** عشان تشوف المستندات المرفوعة.
4. اضغط **Accept** أو **Reject**.
5. **Cancel** بيلغي طلب اتقبل قبل كده (صلاحية **Delete Accept Request**).

**محتاج تأكيد**

- [ ] الطلبات جاية منين (مثلاً المالك بيضيف أقاربه من تطبيق MyPorto).
- [ ] هل **Reject** بيطلب سبب؟ الرسايل بالظبط بعد القبول / الرفض.
- [ ] بعد **Accept**، القريب بيظهر كـ **Owner Relative** في صفحة العميل؟
- [ ] معنى **Cancel** بالظبط (المفترض: إلغاء طلب مقبول).

---

## يتضاف لقسم 12. الفواتير

### إزاي أراجع طلبات الاسترداد؟

1. ادخل **الفواتير** ← **استرداد**.
2. فلتر بـ رقم الفاتورة، رقم بند الفاتورة، الحالة، ERP Reference، ERP Refund Reference، من تاريخ، إلى تاريخ. اضغط **بحث**.
3. كل صف فيه رقم الفاتورة، رقم البند، العميل، الوحدة، المبلغ، طريقة الدفع، مراجع الـ ERP، حالة الاسترداد، طلبه مين، نفّذه مين، سبب الطلب، وسبب الاسترداد.
4. استخدم إجراءات الصف عشان توافق (**Refund**) أو ترفض الطلب.

حالات الفاتورة المرتبطة: **Refund Requested** و **Refunded** و **Partially Refund**.

**محتاج تأكيد**

- [ ] الاسترداد بيتطلب منين أول مرة: من تفاصيل الفاتورة (**بحث الفواتير**) ولا من الصفحة دي (زرار **Refund Request**)؟
- [ ] أسماء إجراءات الموافقة والرفض بالظبط، وهل لازم يتكتب **Refund Reason**.
- [ ] الاسترداد الجزئي بيتعمل إزاي (لكل بند فاتورة؟).
- [ ] الاسترداد المقبول بيأثر على أرقام **نهاية اليوم** للكاشير (Total Refunded)؟

---

## يتضاف لقسم 15. المستخدمين

### إزاي أضيف مستخدم قانوني؟

1. ادخل **المستخدمين** ← **إضافة المستخدمين القانونيين**. عنوان الصفحة **Legal Employees - Add**.
2. اكتب **الاسم بالكامل** و**رقم الموبايل**.
3. اضغط **Add** (أو **Cancel**).

**محتاج تأكيد**

- [ ] المستخدم القانوني بيُستخدم في إيه (المفترض: المحامين اللي بيتختاروا كـ **Assigned Lawyer** في الحظر القانوني).
- [ ] هل بياخد حساب دخول على النظام ولا مجرد بيانات تواصل؟
- [ ] رسالة النجاح بالظبط، وهل **المشروع** بيتحدد تلقائي؟

---

### إزاي ألاقي مستخدم قانوني أو أعدّله؟

1. ادخل **المستخدمين** ← **إدارة المستخدمين القانونيين** (**Legal Employees - Search**).
2. فلتر بـ الاسم بالكامل، رقم الموبايل، الحالة. اضغط **بحث**.
3. النتايج فيها الحالة، الاسم، الموبايل، والمشروع. اضغط **Edit** في الصف عشان تعدّل.

**محتاج تأكيد**

- [ ] أنهي حقول ينفع تتعدل، وإزاي المستخدم القانوني يتوقف (عمود **Status**).

</div>
