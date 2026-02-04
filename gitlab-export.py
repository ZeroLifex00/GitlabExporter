#!/usr/bin/env python3
"""
Export GitLab projects, archived projects (separately), groups, and users to CSV.

Outputs (by default) in ./gitlab_export_<timestamp>/ :
- projects.csv            : active projects, members (username:role)
- archived_projects.csv   : archived projects, members (username:role)  [only if --include-archived]
- groups.csv              : groups, members (username:role)
- users.csv               : users with status and flags (admin/external/bot/etc)

Auth notes (self-managed):
- Exporting ALL users typically requires an admin token (or equivalent permission).
- Group/project member listings depend on token visibility.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import gitlab


ACCESS_LEVELS = {
    10: "Guest",
    20: "Reporter",
    30: "Developer",
    40: "Maintainer",
    50: "Owner",
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def access_level_name(level: Optional[int]) -> str:
    if level is None:
        return ""
    return ACCESS_LEVELS.get(level, str(level))


def safe_get(obj, attr: str, default=None):
    return getattr(obj, attr, default)


def make_gitlab_client(url: str, token: str, ssl_verify: bool) -> gitlab.Gitlab:
    gl = gitlab.Gitlab(url=url, private_token=token, ssl_verify=ssl_verify)
    gl.auth()  # validate token
    return gl


def iter_all(items_list_callable, **kwargs):
    """
    Iterate all pages via python-gitlab using iterator=True.
    """
    return items_list_callable(iterator=True, **kwargs)


def format_members(members_iter) -> str:
    """
    Return semicolon-separated unique member strings: ident:Role
    """
    members_parts: List[str] = []
    for m in members_iter:
        username = safe_get(m, "username", "") or ""
        name = safe_get(m, "name", "") or ""
        access_level = safe_get(m, "access_level", None)
        role = access_level_name(access_level)

        ident = username if username else name
        if not ident:
            ident = f"user_id_{safe_get(m, 'id', '')}"

        members_parts.append(f"{ident}:{role}")

    return ";".join(sorted(set(members_parts)))


def export_projects(
    gl: gitlab.Gitlab,
    out_csv: Path,
    archived: bool,
    members_scope: str,
    sleep_s: float,
):
    """
    Export projects + members + roles.
    archived: if True, export only archived projects; if False export only non-archived.
    members_scope:
      - "all"    : includes inherited members (group/ancestor)
      - "direct" : direct project members only
    """
    label = "archived projects" if archived else "active projects"
    eprint(f"Exporting {label} -> {out_csv.name} ...")

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "project_id",
                "project_name",
                "project_path_with_namespace",
                "http_url_to_repo",
                "default_branch",
                "visibility",
                "archived",
                "members",  # semicolon separated: username:Role
            ],
        )
        writer.writeheader()

        projects = iter_all(gl.projects.list, archived=archived)

        count = 0
        for p in projects:
            count += 1
            proj = gl.projects.get(p.id)

            if members_scope == "all":
                members_iter = iter_all(proj.members_all.list)
            else:
                members_iter = iter_all(proj.members.list)

            writer.writerow(
                {
                    "project_id": proj.id,
                    "project_name": safe_get(proj, "name", ""),
                    "project_path_with_namespace": safe_get(proj, "path_with_namespace", ""),
                    "http_url_to_repo": safe_get(proj, "http_url_to_repo", ""),
                    "default_branch": safe_get(proj, "default_branch", ""),
                    "visibility": safe_get(proj, "visibility", ""),
                    "archived": bool(safe_get(proj, "archived", False)),
                    "members": format_members(members_iter),
                }
            )

            if sleep_s > 0:
                time.sleep(sleep_s)

            if count % 50 == 0:
                eprint(f"  ...{count} projects processed")

    eprint(f"Projects export complete: {out_csv}")


def export_groups(
    gl: gitlab.Gitlab,
    out_csv: Path,
    members_scope: str,
    sleep_s: float,
):
    """
    Export groups + members + roles.
    members_scope:
      - "all"    : includes inherited members (from parent groups)
      - "direct" : direct group members only
    """
    eprint(f"Exporting groups -> {out_csv.name} ...")

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "group_id",
                "group_name",
                "group_full_path",
                "web_url",
                "visibility",
                "parent_id",
                "members",  # semicolon separated: username:Role
            ],
        )
        writer.writeheader()

        groups = iter_all(gl.groups.list)

        count = 0
        for g in groups:
            count += 1
            grp = gl.groups.get(g.id)

            if members_scope == "all":
                members_iter = iter_all(grp.members_all.list)
            else:
                members_iter = iter_all(grp.members.list)

            writer.writerow(
                {
                    "group_id": grp.id,
                    "group_name": safe_get(grp, "name", ""),
                    "group_full_path": safe_get(grp, "full_path", ""),
                    "web_url": safe_get(grp, "web_url", ""),
                    "visibility": safe_get(grp, "visibility", ""),
                    "parent_id": safe_get(grp, "parent_id", ""),
                    "members": format_members(members_iter),
                }
            )

            if sleep_s > 0:
                time.sleep(sleep_s)

            if count % 100 == 0:
                eprint(f"  ...{count} groups processed")

    eprint(f"Groups export complete: {out_csv}")


def export_users(
    gl: gitlab.Gitlab,
    out_csv: Path,
    sleep_s: float,
):
    """
    Export users + status + flags.
    Listing all users typically requires admin rights on self-managed GitLab.
    """
    eprint(f"Exporting users -> {out_csv.name} ...")

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "user_id",
                "username",
                "name",
                "state",          # active / blocked / etc
                "is_admin",
                "external",
                "bot",
                "email",
                "created_at",
                "last_sign_in_at",
            ],
        )
        writer.writeheader()

        users = iter_all(gl.users.list)

        count = 0
        for u in users:
            count += 1
            user = gl.users.get(u.id)

            writer.writerow(
                {
                    "user_id": user.id,
                    "username": safe_get(user, "username", ""),
                    "name": safe_get(user, "name", ""),
                    "state": safe_get(user, "state", ""),
                    "is_admin": bool(safe_get(user, "is_admin", False)),
                    "external": bool(safe_get(user, "external", False)),
                    "bot": bool(safe_get(user, "bot", False)),
                    "email": safe_get(user, "email", ""),
                    "created_at": safe_get(user, "created_at", ""),
                    "last_sign_in_at": safe_get(user, "last_sign_in_at", ""),
                }
            )

            if sleep_s > 0:
                time.sleep(sleep_s)

            if count % 200 == 0:
                eprint(f"  ...{count} users processed")

    eprint(f"Users export complete: {out_csv}")


def main():
    parser = argparse.ArgumentParser(description="Export GitLab projects, groups, and users to CSV.")
    parser.add_argument("--url", default=os.getenv("GITLAB_URL", ""), help="GitLab base URL, e.g. https://gitlab.example.com")
    parser.add_argument("--token", default=os.getenv("GITLAB_TOKEN", ""), help="GitLab personal access token (PAT)")
    parser.add_argument("--outdir", default="", help="Output directory (default: gitlab_export_<timestamp>/)")
    parser.add_argument("--include-archived", action="store_true", help="Also export archived projects to archived_projects.csv")
    parser.add_argument(
        "--members-scope",
        choices=["all", "direct"],
        default="all",
        help='Member listing scope: "all" includes inherited (recommended), "direct" is direct members only.',
    )
    parser.add_argument("--no-ssl-verify", action="store_true", help="Disable SSL verification (not recommended)")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep N seconds between API calls (helps with rate limits)")

    args = parser.parse_args()

    if not args.url:
        eprint("ERROR: GitLab URL not provided. Use --url or set GITLAB_URL.")
        sys.exit(2)
    if not args.token:
        eprint("ERROR: GitLab token not provided. Use --token or set GITLAB_TOKEN.")
        sys.exit(2)

    outdir = Path(args.outdir) if args.outdir else Path(f"gitlab_export_{utc_stamp()}")
    outdir.mkdir(parents=True, exist_ok=True)

    ssl_verify = not args.no_ssl_verify

    eprint(f"Connecting to {args.url} (ssl_verify={ssl_verify}) ...")
    gl = make_gitlab_client(args.url, args.token, ssl_verify=ssl_verify)

    # Active projects always
    export_projects(
        gl=gl,
        out_csv=outdir / "projects.csv",
        archived=False,
        members_scope=args.members_scope,
        sleep_s=args.sleep,
    )

    # Archived projects in separate CSV if requested
    if args.include_archived:
        export_projects(
            gl=gl,
            out_csv=outdir / "archived_projects.csv",
            archived=True,
            members_scope=args.members_scope,
            sleep_s=args.sleep,
        )

    # Groups
    export_groups(
        gl=gl,
        out_csv=outdir / "groups.csv",
        members_scope=args.members_scope,
        sleep_s=args.sleep,
    )

    # Users
    export_users(
        gl=gl,
        out_csv=outdir / "users.csv",
        sleep_s=args.sleep,
    )

    print(str(outdir.resolve()))


if __name__ == "__main__":
    main()
