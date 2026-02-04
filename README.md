# GitLab Exporter

A small Python script to export useful audit/admin data from a **self-hosted GitLab** instance into CSV files.

## What it exports

### Projects (repositories)
- Project name
- Project path with namespace
- HTTP clone URL
- Default branch
- Visibility
- Archived flag
- Assigned users (project members) and their roles (Guest/Reporter/Developer/Maintainer/Owner)

Outputs:
- `projects.csv` (always: **non-archived** projects)
- `archived_projects.csv` (optional: **archived** projects, only when enabled)

To output archived projects too, use the parameter `--archived-projects`:

```
python gitlab-export.py --archived-projects
```

### Groups
- Group name
- Full path
- Web URL
- Visibility
- Parent group ID (if nested)
- Group members and their roles

Output:
- `groups.csv`

### Users
- Username / name
- State (e.g., active/blocked)
- Admin / external / bot flags (where visible)
- Email (often only visible to admins)
- Created date
- Last sign-in date

Output:
- `users.csv`

> **Permissions note (self-hosted GitLab):**
> - Exporting *all* users (and seeing email/admin fields) typically requires an **admin** Personal Access Token.
> - Projects, groups, and member lists depend on what the token is allowed to see.

---

## Requirements
- Python 3.9+ recommended
- `python-gitlab` library

### Environment variables
#### Bash/zsh

```
export GITLAB_URL="https://gitlab.example.com"
export GITLAB_TOKEN="YOUR_PERSONAL_ACCESS_TOKEN"
```

#### Powershell

```
$env:GITLAB_URL="https://gitlab.example.com"
$env:GITLAB_TOKEN="YOUR_PERSONAL_ACCESS_TOKEN"
```