# Administrator provisioning

Administrators are created out of band from a trusted operator shell. Public
registration accepts only student and faculty roles. This workflow has no
default password and refuses to change the role of an existing account.

From `backend`, set the exact database URL that should receive the account and
explicitly enable the one-time CLI. The command displays a sanitized database
label and requires a typed confirmation before it prompts for the account
details. Password entry is hidden and passwords must be at least 16 characters.

```powershell
$env:DATABASE_URL = '<the intended database URL>'
$env:RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING = 'YES'
python .\provision_admin.py
```

Use an operator-controlled secret store for production database credentials.
Do not run this command against a production database until an authorized
operator has independently verified the target and approved the account.
The tool does not print the database URL, password, or bearer tokens.
