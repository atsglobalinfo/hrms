# ATS Legacy Data Migration

One-time migration of the old PHP/CodeIgniter ATS HRMS database export into this Frappe HR
site. The migration logic lives in `hrms/ats_legacy_migration.py` (part of the app source,
so it ships with a normal `git pull` — no manual file copying needed).

## Prerequisites

- `hrms` app installed on the target site (`bench install-app hrms`)
- The Company record this data should belong to already exists
- The phpMyAdmin JSON export (e.g. `legacy_data.json`) copied onto the server, at a path the
  bench process can read

## Running the migration

```bash
bench --site <your-site> execute hrms.ats_legacy_migration.run \
  --kwargs "{'data_path': '/absolute/path/to/legacy_data.json', 'company': 'Exact Company Name', 'default_password': 'SomeTemporaryPassword123'}"
```

- `data_path` — absolute path to the JSON export on the server
- `company` — must exactly match an existing Frappe Company name
- `default_password` — temporary password set on every migrated employee's new User account;
  never commit a real value for this into source control or chat history. Communicate it to
  employees out-of-band and have them change it on first login.

The script prints a JSON report of what was created/skipped/errored per phase. It's safe to
re-run — every phase checks for existing records first, except Employee Checkin bulk-import,
which is skipped entirely once any legacy checkins already exist for the site.

## What it does NOT do

- Does not migrate passwords from the old system (those were MD5 hashes with no recoverable
  plaintext) — all migrated users get the one `default_password` you provide, to be changed on
  first login.
- Does not migrate the `messages` (chat) or `tasks` tables — not present in the JSON export.
- Does not migrate `blog`, `award_content`, `sales`, `site_settings`, or `notification` tables —
  these are bespoke features with no Frappe HR equivalent; build a custom doctype first if
  you want that data brought in later.
- Historical Leave Applications are imported as unsubmitted records (draft, for audit/reference)
  rather than pushed through Frappe's leave-balance validation, since the old system only kept
  a single current balance snapshot, not per-fiscal-year allocations.
