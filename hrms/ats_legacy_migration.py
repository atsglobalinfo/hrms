"""One-time migration of the legacy ATS HRMS (PHP/CodeIgniter) database export into Frappe HR.

Usage (run once per site, after `bench get-app`/`bench install-app hrms` and after copying
the phpMyAdmin JSON export to the path given by `data_path`):

    bench --site <site> execute hrms.ats_legacy_migration.run \
        --kwargs "{'data_path': '/path/to/legacy_data.json', 'company': 'Your Company', 'default_password': 'Temp@Pass123'}"

Safe to re-run: every phase checks for existing records before creating new ones, except
Employee Checkin (bulk-inserted for performance) which is skipped entirely if any legacy
checkins already exist.
"""

import json

import frappe
from frappe.permissions import add_permission, update_permission_property
from frappe.utils import add_months, getdate

LEAVE_TYPE_MAP = {"1": "Casual Leave", "2": "Sick Leave", "3": "Privilege Leave"}
LEAVE_STATUS_MAP = {"1": "Open", "2": "Approved", "3": "Rejected", "4": "Cancelled"}
GENDER_MAP = {"male": "Male", "female": "Female", "other": "Other"}
ASSET_CATEGORIES = [
	"Laptop", "Mouse", "PenDrive", "KeyBoard", "Charger", "Printer", "Monitor",
	"Hard-Disk", "Ram", "Mouse pad", "Projector", "Mobile", "Domain", "Others",
]
DEPLOYED_AT = ["ATS-GLOBAL-TECHSOFT", "IMTAC", "NANOTON", "CARE-EDGE", "3-Info-Tech"]
LEGACY_ROLE_PREFIX = "ATS "  # avoid colliding with Frappe/HRMS's own built-in role names

REPORT = {}


def bump(phase, key="created", n=1):
	REPORT.setdefault(phase, {"created": 0, "skipped": 0, "errors": []})
	REPORT[phase][key] += n


def log_error(phase, msg):
	REPORT.setdefault(phase, {"created": 0, "skipped": 0, "errors": []})
	REPORT[phase]["errors"].append(msg)


def clean(v):
	return v.strip() if isinstance(v, str) else (v or "")


def safe_float(v):
	try:
		return float(str(v).strip()) if v not in (None, "") else 0
	except Exception:
		return 0


def load_tables(data_path):
	with open(data_path) as f:
		data = json.load(f)
	return {e["name"]: e.get("data", []) for e in data if e.get("type") == "table"}


# ---------- setup ----------

def ensure_custom_field(dt, fieldname, label, fieldtype="Data", insert_after=None, unique=0, hidden=0):
	if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
		return
	doc = {
		"doctype": "Custom Field",
		"dt": dt,
		"fieldname": fieldname,
		"label": label,
		"fieldtype": fieldtype,
		"unique": unique,
		"hidden": hidden,
	}
	if insert_after:
		doc["insert_after"] = insert_after
	frappe.get_doc(doc).insert(ignore_permissions=True)


def ensure_fiscal_years():
	for name, start, end in [
		("2022-2023", "2022-04-01", "2023-03-31"),
		("2023-2024", "2023-04-01", "2024-03-31"),
		("2024-2025", "2024-04-01", "2025-03-31"),
		("2025-2026", "2025-04-01", "2026-03-31"),
	]:
		if not frappe.db.exists("Fiscal Year", name):
			frappe.get_doc({"doctype": "Fiscal Year", "year": name, "year_start_date": start, "year_end_date": end}).insert(
				ignore_permissions=True
			)


_component_cache = {}


def ensure_salary_component(name, ctype):
	if name in _component_cache:
		return _component_cache[name]
	if not frappe.db.exists("Salary Component", name):
		frappe.get_doc({"doctype": "Salary Component", "salary_component": name, "type": ctype}).insert(
			ignore_permissions=True
		)
	_component_cache[name] = name
	return name


def ensure_gender(g):
	if not g:
		return None
	mapped = GENDER_MAP.get(g.lower(), g.title())
	if not frappe.db.exists("Gender", mapped):
		try:
			frappe.get_doc({"doctype": "Gender", "gender": mapped}).insert(ignore_permissions=True)
		except Exception:
			return None
	return mapped


def ensure_designation(name):
	name = clean(name) or "Employee"
	if not frappe.db.exists("Designation", name):
		frappe.get_doc({"doctype": "Designation", "designation_name": name}).insert(ignore_permissions=True)
	return name


def ensure_legacy_asset_doctype():
	if frappe.db.exists("DocType", "Legacy Asset"):
		return
	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": "Legacy Asset",
			"module": "HR",
			"custom": 1,
			"naming_rule": "Autoincrement",
			"autoname": "autoincrement",
			"fields": [
				{"fieldname": "category", "fieldtype": "Select", "options": "\n".join(ASSET_CATEGORIES), "label": "Category"},
				{"fieldname": "asset_name", "fieldtype": "Data", "label": "Name"},
				{"fieldname": "model", "fieldtype": "Data", "label": "Model"},
				{"fieldname": "description", "fieldtype": "Small Text", "label": "Description"},
				{"fieldname": "status", "fieldtype": "Select", "options": "Active\nInactive", "label": "Status"},
				{"fieldname": "serial_no", "fieldtype": "Data", "label": "Serial No"},
				{"fieldname": "owned_by", "fieldtype": "Select", "options": "\n".join(DEPLOYED_AT), "label": "Deployed At"},
				{"fieldname": "warranty", "fieldtype": "Data", "label": "Warranty (months)"},
				{"fieldname": "warranty_expiry", "fieldtype": "Date", "label": "Warranty Expiry"},
				{"fieldname": "employee", "fieldtype": "Link", "options": "Employee", "label": "Assigned Employee"},
				{"fieldname": "entry_date", "fieldtype": "Date", "label": "Entry Date"},
				{"fieldname": "assign_date", "fieldtype": "Date", "label": "Assign Date"},
				{"fieldname": "mac_id", "fieldtype": "Data", "label": "MAC ID"},
				{"fieldname": "legacy_image_filenames", "fieldtype": "Small Text", "label": "Legacy Image Filenames (unavailable)"},
			],
			"permissions": [{"role": "HR Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
		}
	).insert(ignore_permissions=True)


def ensure_company_expense_doctype():
	if frappe.db.exists("DocType", "Company Expense"):
		return
	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": "Company Expense",
			"module": "HR",
			"custom": 1,
			"naming_rule": "Autoincrement",
			"autoname": "autoincrement",
			"fields": [
				{"fieldname": "vendor_name", "fieldtype": "Data", "label": "Vendor / Company Name", "reqd": 1},
				{"fieldname": "invoice_id", "fieldtype": "Data", "label": "Invoice ID"},
				{"fieldname": "invoice_date", "fieldtype": "Date", "label": "Invoice Date"},
				{"fieldname": "gst_number", "fieldtype": "Data", "label": "GST Number"},
				{"fieldname": "bill_amount", "fieldtype": "Currency", "label": "Bill Amount"},
				{"fieldname": "bill_image", "fieldtype": "Attach Image", "label": "Bill Image"},
				{"fieldname": "description", "fieldtype": "Small Text", "label": "Description"},
				{"fieldname": "status", "fieldtype": "Select", "options": "Active\nInactive", "label": "Status", "default": "Active"},
				{"fieldname": "logged_by", "fieldtype": "Link", "options": "Employee", "label": "Logged By"},
				{"fieldname": "company", "fieldtype": "Link", "options": "Company", "label": "Company"},
				{"fieldname": "logged_date", "fieldtype": "Date", "label": "Logged Date"},
			],
			"permissions": [{"role": "HR Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
		}
	).insert(ignore_permissions=True)


def ensure_warranty_reminder_script():
	if frappe.db.exists("Server Script", "Legacy Asset Warranty Reminder"):
		return
	frappe.get_doc(
		{
			"doctype": "Server Script",
			"name": "Legacy Asset Warranty Reminder",
			"script_type": "Scheduler Event",
			"event_frequency": "Daily",
			"disabled": 0,
			"script": (
				"from frappe.utils import today, add_days\n"
				"upcoming = add_days(today(), 7)\n"
				"assets = frappe.get_all('Legacy Asset', "
				"filters={'warranty_expiry': ['between', [today(), upcoming]]}, "
				"fields=['name', 'asset_name', 'employee', 'warranty_expiry'])\n"
				"hr_users = frappe.get_all('Has Role', filters={'role': 'HR Manager'}, fields=['parent'])\n"
				"recipients = list(set(u.parent for u in hr_users))\n"
				"for a in assets:\n"
				"    if recipients:\n"
				"        frappe.sendmail(\n"
				"            recipients=recipients,\n"
				"            subject=f'Asset warranty expiring soon: {a.asset_name or a.name}',\n"
				"            message=f'Asset {a.name} ({a.asset_name}) warranty expires on {a.warranty_expiry}.',\n"
				"        )\n"
			),
		}
	).insert(ignore_permissions=True)


def ensure_default_address_template():
	if frappe.db.exists("Address Template", {"is_default": 1}):
		return
	if frappe.db.exists("Address Template", "India"):
		frappe.db.set_value("Address Template", "India", "is_default", 1)
		return
	frappe.get_doc(
		{
			"doctype": "Address Template",
			"country": "India",
			"is_default": 1,
			"template": (
				"{{ address_line1 }}<br>{% if address_line2 %}{{ address_line2 }}<br>{% endif %}"
				"{{ city }}<br>{% if state %}{{ state }}<br>{% endif %}"
				"{% if pincode %}{{ pincode }}<br>{% endif %}{{ country }}"
			),
		}
	).insert(ignore_permissions=True)


def setup(company):
	ensure_custom_field("Employee", "custom_legacy_user_id", "Legacy User ID", unique=1, insert_after="employee_number")
	ensure_custom_field("Employee", "custom_bank_account_holder_name", "Bank Account Holder Name", insert_after="ifsc_code")
	ensure_fiscal_years()
	for comp in ["Conveyance", "Medical Allowance", "Special Allowances"]:
		if not frappe.db.exists("Salary Component", comp):
			frappe.get_doc({"doctype": "Salary Component", "salary_component": comp, "type": "Earning"}).insert(
				ignore_permissions=True
			)
	ensure_legacy_asset_doctype()
	ensure_custom_field("Legacy Asset", "custom_legacy_asset_id", "Legacy Asset ID", unique=1, insert_after="mac_id")
	ensure_company_expense_doctype()
	ensure_warranty_reminder_script()
	ensure_default_address_template()
	frappe.db.commit()


def normalize_deployed_at(value):
	value = clean(value)
	if not value:
		return ""
	normalized = value.upper().replace(" ", "-")
	for canonical in DEPLOYED_AT:
		if canonical.upper() == normalized:
			return canonical
	return ""


# ---------- employees ----------

def import_employees(tables, company):
	bank_by_user = {r["userId"]: r for r in tables.get("bank", [])}
	legacy_map = {}

	for row in tables.get("user", []):
		uid = row["userId"]
		existing = frappe.db.get_value("Employee", {"custom_legacy_user_id": uid}, "name")
		if existing:
			legacy_map[uid] = existing
			bump("employees", "skipped")
			continue
		try:
			first = clean(row.get("firstName")) or "Employee"
			middle = clean(row.get("middleName"))
			last = clean(row.get("lastName"))
			full_name = " ".join(p for p in [first, middle, last] if p)

			gender = ensure_gender(row.get("gender"))
			designation = ensure_designation(row.get("designation"))

			dob = row.get("dob")
			dob = getdate(dob[:10]) if dob else None

			checkins = [
				c["date"] for c in tables.get("daily_checkin_checkout", [])
				if c.get("userId") == uid and c.get("date")
			]
			doj = getdate(min(checkins)[:10]) if checkins else getdate("2023-01-01")

			emp = frappe.new_doc("Employee")
			emp.custom_legacy_user_id = uid
			emp.employee_name = full_name
			emp.first_name = first
			if middle:
				emp.middle_name = middle
			if last:
				emp.last_name = last
			emp.company = company
			# legacy status: 1 = Active (green), 0 = Inactive (red) per old admin UI badge logic
			emp.status = "Active" if row.get("status") == "1" else "Inactive"
			emp.designation = designation
			emp.date_of_joining = doj
			if dob:
				emp.date_of_birth = dob
			if gender:
				emp.gender = gender
			email = clean(row.get("emailAddress"))
			if email:
				emp.personal_email = email
				emp.company_email = email
			phone = clean(row.get("phoneNo"))
			if phone:
				emp.cell_number = phone
			bg = clean(row.get("blood_group"))
			if bg:
				emp.blood_group = bg
			eid = clean(row.get("employeeId"))
			if eid:
				emp.employee_number = eid

			bank = bank_by_user.get(uid)
			if bank:
				if clean(bank.get("bankName")):
					emp.bank_name = clean(bank.get("bankName"))
					emp.salary_mode = "Bank"
				if clean(bank.get("accountNumber")):
					emp.bank_ac_no = clean(bank.get("accountNumber"))
				if clean(bank.get("ifscCode")):
					emp.ifsc_code = clean(bank.get("ifscCode"))
				if clean(bank.get("userNameInBank")):
					emp.custom_bank_account_holder_name = clean(bank.get("userNameInBank"))

			salary_row = next((r for r in tables.get("salary_structure", []) if r["userId"] == uid), None)
			if salary_row:
				ctc = safe_float(salary_row.get("netIncome")) or safe_float(salary_row.get("base"))
				if ctc:
					emp.ctc = ctc
					emp.salary_currency = "INR"

			emp.flags.ignore_mandatory = True
			emp.insert(ignore_permissions=True)
			legacy_map[uid] = emp.name
			bump("employees")
		except Exception as e:
			log_error("employees", f"{uid}: {e}")

	frappe.db.commit()

	for row in tables.get("user_manager", []):
		try:
			emp_name = legacy_map.get(row["userId"])
			mgr_name = legacy_map.get(row["managerId"])
			if emp_name and mgr_name and emp_name != mgr_name:
				frappe.db.set_value("Employee", emp_name, "reports_to", mgr_name)
				bump("reports_to")
		except Exception as e:
			log_error("reports_to", str(e))

	frappe.db.commit()
	return legacy_map


# ---------- addresses (standalone, idempotent) ----------

def import_addresses(tables, legacy_map):
	address_by_user = {r["userId"]: r for r in tables.get("address", [])}
	name_by_user = {
		r["userId"]: " ".join(p for p in [clean(r.get("firstName")), clean(r.get("middleName")), clean(r.get("lastName"))] if p)
		for r in tables.get("user", [])
	}

	for uid, emp_name in legacy_map.items():
		addr = address_by_user.get(uid)
		if not addr or not (clean(addr.get("line1")) or clean(addr.get("city"))):
			continue
		already = frappe.db.sql(
			"""select 1 from `tabDynamic Link` where link_doctype='Employee' and link_name=%s
			   and parenttype='Address' limit 1""",
			emp_name,
		)
		if already:
			bump("addresses", "skipped")
			continue
		try:
			a = frappe.new_doc("Address")
			a.address_title = name_by_user.get(uid) or emp_name
			a.address_type = "Current"
			a.address_line1 = clean(addr.get("line1")) or "NA"
			a.address_line2 = clean(addr.get("line2"))
			a.city = clean(addr.get("city")) or "NA"
			a.state = clean(addr.get("state"))
			a.pincode = clean(addr.get("pincode"))
			a.country = clean(addr.get("country")) or "India"
			a.append("links", {"link_doctype": "Employee", "link_name": emp_name})
			a.flags.ignore_mandatory = True
			a.insert(ignore_permissions=True)
			bump("addresses")
		except Exception as e:
			log_error("addresses", f"{uid}: {e}")
	frappe.db.commit()


# ---------- holidays ----------

def import_holidays(tables, company):
	rows = tables.get("holidays", [])
	if not rows:
		return
	type_map = {"0": "National", "1": "State", "2": "Festival"}
	dates = sorted(set(r["date"][:10] for r in rows if r.get("date")))
	if not dates:
		return
	name = "Legacy Holidays 2023-2027"
	if not frappe.db.exists("Holiday List", name):
		hl = frappe.new_doc("Holiday List")
		hl.holiday_list_name = name
		hl.from_date = dates[0]
		hl.to_date = "2027-03-31"
		seen = set()
		for r in rows:
			d = r.get("date")
			if not d:
				continue
			d = d[:10]
			if d in seen:
				continue
			seen.add(d)
			htype = type_map.get(r.get("type"), "")
			desc = clean(r.get("details")) or "Holiday"
			hl.append("holidays", {"holiday_date": d, "description": f"[{htype}] {desc}" if htype else desc})
		hl.flags.ignore_mandatory = True
		hl.insert(ignore_permissions=True)
		bump("holidays", n=len(seen))

	if not frappe.get_all("Holiday List Assignment", filters={"applicable_for": "Company", "assigned_to": company, "docstatus": 1}):
		hla = frappe.new_doc("Holiday List Assignment")
		hla.applicable_for = "Company"
		hla.assigned_to = company
		hla.holiday_list = name
		hla.from_date = dates[0]
		hla.insert(ignore_permissions=True)
		hla.submit()

	if not frappe.db.get_value("Company", company, "default_holiday_list"):
		frappe.db.set_value("Company", company, "default_holiday_list", name)

	frappe.db.commit()


# ---------- leave ----------

def import_leave_allocations(tables, legacy_map):
	fy = ("2026-04-01", "2027-03-31")
	used_field = {"Casual Leave": "casual_leaves_used", "Sick Leave": "sick_leaves_used", "Privilege Leave": "earned_leaves_used"}
	alloc_field = {"Casual Leave": "casual_leaves", "Sick Leave": "sick_leaves", "Privilege Leave": "earned_leaves"}

	for row in tables.get("employeeleave", []):
		emp_name = legacy_map.get(row["userId"])
		if not emp_name:
			bump("leave_allocations", "skipped")
			continue
		for leave_type in alloc_field:
			try:
				allocated = safe_float(row.get(alloc_field[leave_type]))
				used = safe_float(row.get(used_field[leave_type]))
				remaining = max(allocated - used, 0)
				if remaining <= 0:
					continue
				if frappe.db.exists("Leave Allocation", {"employee": emp_name, "leave_type": leave_type, "from_date": fy[0]}):
					continue
				la = frappe.new_doc("Leave Allocation")
				la.employee = emp_name
				la.leave_type = leave_type
				la.from_date = fy[0]
				la.to_date = fy[1]
				la.new_leaves_allocated = remaining
				la.flags.ignore_mandatory = True
				la.insert(ignore_permissions=True)
				try:
					la.submit()
				except Exception:
					pass
				bump("leave_allocations")
			except Exception as e:
				log_error("leave_allocations", f"{row['userId']}/{leave_type}: {e}")
	frappe.db.commit()


def import_leave_applications(tables, legacy_map, company):
	user_to_employee_email = {
		r.custom_legacy_user_id: r.user_id
		for r in frappe.get_all("Employee", filters={"custom_legacy_user_id": ["!=", ""]}, fields=["custom_legacy_user_id", "user_id"])
	}
	for row in tables.get("appliedleave", []):
		emp_name = legacy_map.get(row["userId"])
		if not emp_name:
			bump("leave_applications", "skipped")
			continue
		try:
			la = frappe.new_doc("Leave Application")
			la.employee = emp_name
			la.leave_type = LEAVE_TYPE_MAP.get(row.get("leaveType"), "Casual Leave")
			la.from_date = row["fromDate"][:10]
			la.to_date = row["toDate"][:10]
			la.status = LEAVE_STATUS_MAP.get(row.get("status"), "Open")
			la.description = clean(row.get("reason"))
			la.company = company
			approver_email = user_to_employee_email.get(row.get("approvedBy"))
			if approver_email:
				la.leave_approver = approver_email
			la.flags.ignore_validate = True
			la.flags.ignore_mandatory = True
			la.insert(ignore_permissions=True)
			bump("leave_applications")
		except Exception as e:
			log_error("leave_applications", f"{row.get('id')}: {e}")
	frappe.db.commit()


# ---------- checkins ----------

def import_checkins(tables, legacy_map):
	if frappe.db.sql(
		"""select count(*) from `tabEmployee Checkin` ec join `tabEmployee` e on ec.employee = e.name
           where e.custom_legacy_user_id != ''"""
	)[0][0] > 0:
		REPORT["checkins"] = {"created": 0, "skipped": "already migrated", "errors": []}
		return

	batch = []
	for row in tables.get("daily_checkin_checkout", []):
		emp_name = legacy_map.get(row["userId"])
		if not emp_name or not row.get("date"):
			continue
		date = row["date"]
		for time_field, log_type, ip_field in [
			("checkin_time", "IN", "ip_address_check_in"),
			("checkout_time", "OUT", "ip_address_check_out"),
		]:
			if row.get(time_field):
				batch.append({
					"name": frappe.generate_hash(length=10),
					"employee": emp_name,
					"log_type": log_type,
					"time": f"{date} {row[time_field]}",
					"device_id": clean(row.get(ip_field)),
					"docstatus": 0,
					"owner": "Administrator",
					"modified_by": "Administrator",
					"creation": frappe.utils.now(),
					"modified": frappe.utils.now(),
				})

	fields = ["name", "employee", "log_type", "time", "device_id", "docstatus", "owner", "modified_by", "creation", "modified"]
	CHUNK = 2000
	total = 0
	for i in range(0, len(batch), CHUNK):
		chunk = batch[i : i + CHUNK]
		values = [[r[f] for f in fields] for r in chunk]
		frappe.db.bulk_insert("Employee Checkin", fields=fields, values=values, ignore_duplicates=True)
		total += len(chunk)
		frappe.db.commit()
	REPORT["checkins"] = {"created": total, "skipped": 0, "errors": []}


# ---------- salary ----------

def import_salary(tables, legacy_map, company):
	payslip_structures = {r["userId"]: r for r in tables.get("payslip_structure", [])}

	for uid, ps in payslip_structures.items():
		emp_name = legacy_map.get(uid)
		if not emp_name:
			continue
		try:
			earnings = json.loads(ps.get("earnings") or "{}")
			deductions = json.loads(ps.get("deductions") or "{}")
			struct_name = f"Legacy Structure - {emp_name}"
			if frappe.db.exists("Salary Structure", struct_name):
				continue

			ss = frappe.new_doc("Salary Structure")
			ss.name = struct_name
			ss.company = company
			ss.is_active = "Yes"
			ss.payroll_frequency = "Monthly"

			for n, a in zip(earnings.get("earning_name") or [], earnings.get("earning_amt") or []):
				if clean(n):
					ss.append("earnings", {"salary_component": ensure_salary_component(clean(n), "Earning"), "amount": safe_float(a)})
			for n, a in zip(deductions.get("deductions_name") or [], deductions.get("deductions_amt") or []):
				if clean(n):
					ss.append("deductions", {"salary_component": ensure_salary_component(clean(n), "Deduction"), "amount": safe_float(a)})

			ss.flags.ignore_validate = True
			ss.flags.ignore_mandatory = True
			ss.insert(ignore_permissions=True)
			ss.submit()
			bump("salary_structures")

			base_row = next((r for r in tables.get("salary_structure", []) if r["userId"] == uid), None)
			sa = frappe.new_doc("Salary Structure Assignment")
			sa.employee = emp_name
			sa.salary_structure = ss.name
			sa.company = company
			sa.from_date = frappe.db.get_value("Employee", emp_name, "date_of_joining")
			sa.base = safe_float(base_row.get("base")) if base_row else 0
			sa.flags.ignore_validate = True
			sa.flags.ignore_mandatory = True
			sa.insert(ignore_permissions=True)
			sa.submit()
			bump("salary_assignments")
		except Exception as e:
			log_error("salary_structures", f"{uid}: {e}")

	frappe.db.commit()

	for row in tables.get("payslip", []):
		emp_name = legacy_map.get(row["userId"])
		if not emp_name:
			continue
		try:
			slip_data = json.loads(row.get("payslip") or "{}")
			slip = frappe.new_doc("Salary Slip")
			slip.employee = emp_name
			slip.company = company
			slip.posting_date = row["date"]
			slip.start_date = row["date"][:8] + "01"
			slip.end_date = row["date"]
			slip.payroll_frequency = "Monthly"

			for n, a in (slip_data.get("earnings") or {}).items():
				if clean(n):
					slip.append("earnings", {"salary_component": ensure_salary_component(clean(n), "Earning"), "amount": safe_float(a)})
			for n, a in (slip_data.get("deductions") or {}).items():
				if clean(n):
					slip.append("deductions", {"salary_component": ensure_salary_component(clean(n), "Deduction"), "amount": safe_float(a)})

			slip.gross_pay = safe_float(slip_data.get("gross"))
			slip.total_deduction = safe_float(slip_data.get("totalDeductions"))
			slip.net_pay = safe_float(slip_data.get("netarnings") or slip_data.get("netEarnings"))
			slip.flags.ignore_validate = True
			slip.flags.ignore_mandatory = True
			slip.insert(ignore_permissions=True)
			bump("salary_slips")
		except Exception as e:
			log_error("salary_slips", f"{row.get('id')}: {e}")

	frappe.db.commit()


# ---------- expenses & assets ----------

def import_expenses(tables, legacy_map, company):
	if not frappe.db.exists("Expense Claim Type", "Legacy Expense"):
		frappe.get_doc({"doctype": "Expense Claim Type", "expense_type": "Legacy Expense"}).insert(ignore_permissions=True)
	default_expense_account = frappe.db.get_value(
		"Account", {"company": company, "account_name": "Miscellaneous Expenses", "is_group": 0}, "name"
	)
	if default_expense_account:
		type_doc = frappe.get_doc("Expense Claim Type", "Legacy Expense")
		if company not in [a.company for a in type_doc.accounts]:
			type_doc.append("accounts", {"company": company, "default_account": default_expense_account})
			type_doc.save(ignore_permissions=True)

	for row in tables.get("expenses", []):
		try:
			emp_name = legacy_map.get(row["userId"])
			ce = frappe.new_doc("Company Expense")
			ce.vendor_name = clean(row.get("company_name")) or "Unknown"
			ce.invoice_id = clean(row.get("invoice_id"))
			if row.get("invoice_date"):
				ce.invoice_date = row["invoice_date"][:10]
			ce.gst_number = clean(row.get("gst_number"))
			ce.bill_amount = safe_float(row.get("bill_amount"))
			ce.description = clean(row.get("description"))
			ce.status = "Active"
			ce.company = company
			if emp_name:
				ce.logged_by = emp_name
			if row.get("created_date"):
				ce.logged_date = row["created_date"][:10]
			ce.flags.ignore_mandatory = True
			ce.insert(ignore_permissions=True)
			bump("company_expenses")
		except Exception as e:
			log_error("company_expenses", f"{row.get('id')}: {e}")
	frappe.db.commit()


def import_assets(tables, legacy_map):
	for row in tables.get("assets", []):
		legacy_id = row.get("id")
		if legacy_id and frappe.db.exists("Legacy Asset", {"custom_legacy_asset_id": legacy_id}):
			bump("assets", "skipped")
			continue
		try:
			emp_name = legacy_map.get(row.get("userId"))
			a = frappe.new_doc("Legacy Asset")
			a.custom_legacy_asset_id = legacy_id
			a.category = clean(row.get("category"))
			a.asset_name = clean(row.get("name"))
			a.model = clean(row.get("model"))
			a.description = clean(row.get("description"))
			a.status = clean(row.get("status")) or "Active"
			a.serial_no = clean(row.get("serialno"))
			a.owned_by = normalize_deployed_at(row.get("ownedby"))
			a.warranty = clean(row.get("warranty"))
			a.legacy_image_filenames = clean(row.get("imagesurl"))
			if emp_name:
				a.employee = emp_name
			if row.get("entryDate"):
				a.entry_date = row["entryDate"][:10]
				if a.warranty:
					try:
						a.warranty_expiry = add_months(getdate(a.entry_date), int(a.warranty))
					except Exception:
						pass
			if row.get("assigndate"):
				a.assign_date = row["assigndate"][:10]
			a.mac_id = clean(row.get("macId"))
			a.flags.ignore_mandatory = True
			a.insert(ignore_permissions=True)
			bump("assets")
		except Exception as e:
			log_error("assets", f"{row.get('id')}: {e}")
	frappe.db.commit()


# ---------- roles, permissions, users ----------

RESOURCE_DOCTYPE_MAP = {
	"User": "Employee",
	"AppliedLeave": "Leave Application",
	"ApproveLeave": "Leave Application",
	"EmployeeLeave": "Leave Allocation",
	"AssetsControl": "Legacy Asset",
	"Expense": "Company Expense",
	"Payslip": "Salary Slip",
	"Salary": "Salary Structure",
	"Project": "Project",
	"TimeSheet": "Employee Checkin",
	"TodaysAttendanceList": "Employee Checkin",
}


def import_roles_and_permissions(tables):
	role_id_to_name = {}
	for r in tables["role"]:
		# prefixed to avoid colliding with Frappe/HRMS's own built-in role names (e.g. "Employee")
		name = f"{LEGACY_ROLE_PREFIX}{r['name']}"
		role_id_to_name[r["roleId"]] = name
		if not frappe.db.exists("Role", name):
			frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(ignore_permissions=True)
			bump("roles")
	frappe.db.commit()

	for row in tables["permission"]:
		doctype = RESOURCE_DOCTYPE_MAP.get(row["resourceName"])
		if not doctype:
			bump("permissions", "skipped")
			continue
		role = role_id_to_name.get(row["roleId"])
		if not role:
			continue
		try:
			perm = json.loads(row["resourcePermission"])
			flags = {p["name"]: str(p["value"]) in ("1", "true", "True") for p in perm.get("data", [])}
			if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
				add_permission(doctype, role, 0)
			update_permission_property(doctype, role, 0, "read", 1 if flags.get("View") else 0)
			update_permission_property(doctype, role, 0, "write", 1 if flags.get("Update") else 0)
			update_permission_property(doctype, role, 0, "create", 1 if flags.get("Add") else 0)
			update_permission_property(doctype, role, 0, "delete", 1 if flags.get("Delete") else 0)
			bump("permissions")
		except Exception as e:
			log_error("permissions", f"{row['resourceName']}/{row['roleId']}: {e}")
	frappe.db.commit()
	return role_id_to_name


def import_users_and_role_assignments(tables, legacy_map, role_id_to_name, default_password):
	legacy_employee = {
		r.custom_legacy_user_id: r
		for r in frappe.get_all(
			"Employee",
			filters={"custom_legacy_user_id": ["!=", ""]},
			fields=["name", "custom_legacy_user_id", "personal_email", "first_name", "last_name"],
		)
	}

	uid_to_user = {}
	for uid, emp in legacy_employee.items():
		email = emp.personal_email
		if not email:
			bump("users", "skipped")
			continue
		if frappe.db.exists("User", email):
			uid_to_user[uid] = email
			bump("users", "skipped")
			continue
		try:
			u = frappe.new_doc("User")
			u.email = email
			u.first_name = emp.first_name or "Employee"
			u.last_name = emp.last_name or ""
			u.send_welcome_email = 0
			u.enabled = 1
			u.new_password = default_password
			u.insert(ignore_permissions=True)
			frappe.db.set_value("Employee", emp.name, "user_id", email)
			uid_to_user[uid] = email
			bump("users")
		except Exception as e:
			log_error("users", f"{uid}: {e}")
	frappe.db.commit()

	assigned = 0
	for row in tables["user_role"]:
		user_email = uid_to_user.get(row["userId"])
		role = role_id_to_name.get(row["roleId"])
		if not user_email or not role:
			continue
		try:
			udoc = frappe.get_doc("User", user_email)
			if not any(r.role == role for r in udoc.roles):
				udoc.append("roles", {"role": role})
				udoc.save(ignore_permissions=True)
				assigned += 1
		except Exception as e:
			log_error("role_assignments", f"{row['userId']}/{row['roleId']}: {e}")
	frappe.db.commit()
	REPORT["role_assignments_applied"] = assigned


# ---------- entrypoint ----------

def run(data_path, company, default_password):
	"""
	:param data_path: absolute path to the phpMyAdmin JSON export on this server
	:param company: exact Frappe Company name all migrated records should belong to
	:param default_password: temporary password set on every migrated employee's User account
	    (never hardcode this in source; pass it at the call site, e.g. via --kwargs)
	"""
	tables = load_tables(data_path)
	setup(company)
	legacy_map = import_employees(tables, company)
	import_addresses(tables, legacy_map)
	import_holidays(tables, company)
	import_leave_allocations(tables, legacy_map)
	import_leave_applications(tables, legacy_map, company)
	import_checkins(tables, legacy_map)
	import_salary(tables, legacy_map, company)
	import_expenses(tables, legacy_map, company)
	import_assets(tables, legacy_map)
	role_id_to_name = import_roles_and_permissions(tables)
	import_users_and_role_assignments(tables, legacy_map, role_id_to_name, default_password)

	print("=====MIGRATION_REPORT_START=====")
	print(json.dumps(REPORT, indent=2, default=str))
	print("=====MIGRATION_REPORT_END=====")


def build_legacy_map():
	rows = frappe.get_all("Employee", filters={"custom_legacy_user_id": ["!=", ""]}, fields=["name", "custom_legacy_user_id"])
	return {r.custom_legacy_user_id: r.name for r in rows}


def run_addresses_and_assets(data_path):
	"""Resume just the two phases that had bugs on first run (addresses, assets) - idempotent."""
	tables = load_tables(data_path)
	setup(next(iter(frappe.get_all("Company", pluck="name")), None))
	legacy_map = build_legacy_map()
	import_addresses(tables, legacy_map)
	import_assets(tables, legacy_map)

	print("=====MIGRATION_REPORT_START=====")
	print(json.dumps(REPORT, indent=2, default=str))
	print("=====MIGRATION_REPORT_END=====")
