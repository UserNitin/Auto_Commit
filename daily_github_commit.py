
from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_CSV = Path(__file__).resolve().with_name("repositories.csv")
GIT_USERS_CSV = Path(__file__).resolve().with_name("git_users.csv")
CSV_COLUMNS = (
    "name",
    "path",
    "remote_url",
    "auto_commit",
    "auto_push",
    "schedule_time",
    "commit_message",
)
GIT_USER_COLUMNS = ("profile_name", "git_name", "git_email", "github_username")
Repository = str | Path


@dataclass
class CommitResult:

    hexsha: str
    message: str


def _git_bash_path() -> str:
    candidates = [
        os.environ.get("GIT_BASH_PATH", ""),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        str(Path.home() / "AppData/Local/Programs/Git/bin/bash.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    discovered = shutil.which("bash.exe")
    if discovered:
        return discovered
    raise ValueError(
        "Git Bash was not found. Install Git for Windows or set GIT_BASH_PATH."
    )


def _run_in_git_bash(
    arguments: list[str],
    *,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [_git_bash_path(), "-lc", 'exec "$@"', "gitcommit", *arguments],
        capture_output=capture_output,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "Command failed.").strip()
        raise ValueError(detail)
    return result


def _run_git(
    repository: Repository,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    path = str(Path(repository).expanduser().resolve())
    return _run_in_git_bash(
        ["git", "-C", path, *arguments],
        check=check,
    )


def _authenticated_github_accounts() -> list[str]:
    result = _run_in_git_bash(
        ["git", "credential-manager", "github", "list"]
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _login_github_account(username: str) -> None:
    if username.casefold() in {
        account.casefold() for account in _authenticated_github_accounts()
    }:
        return
    print(f"Opening GitHub browser login for {username}...")
    _run_in_git_bash(
        [
            "git",
            "credential-manager",
            "github",
            "login",
            "--username",
            username,
            "--browser",
        ],
        capture_output=False,
    )
    if username.casefold() not in {
        account.casefold() for account in _authenticated_github_accounts()
    }:
        raise ValueError(
            f"Git Credential Manager did not save the {username} account."
        )


def add_repository(
    name: str,
    path: str | Path,
    remote_url: str,
    auto_commit: bool,
    auto_push: bool,
    schedule_time: str,
    commit_message: str,
    csv_file: str | Path = DEFAULT_CSV,
) -> dict[str, str | bool]:
    name = name.strip()
    remote_url = remote_url.strip()
    schedule_time = schedule_time.strip()
    commit_message = commit_message.strip()
    folder_path = Path(path).expanduser()

    if not name:
        raise ValueError("name is required.")
    if not folder_path.is_absolute():
        raise ValueError("path must be an absolute path.")
    if not remote_url:
        raise ValueError("remote_url is required.")
    if not isinstance(auto_commit, bool) or not isinstance(auto_push, bool):
        raise ValueError("auto_commit and auto_push must be bool values.")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule_time):
        raise ValueError("schedule_time must use 24-hour HH:MM format.")
    if not commit_message:
        raise ValueError("commit_message is required.")
    folder = str(folder_path.resolve())

    csv_path = Path(csv_file)
    repositories = load_repositories(csv_path)
    for item in repositories:
        if str(item["name"]).casefold() == name.casefold():
            raise ValueError(f"Repository name is already saved: {name}")
        if Path(str(item["path"])).resolve() == Path(folder):
            raise ValueError(f"Repository path is already saved: {folder}")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "name": name,
            "path": folder,
            "remote_url": remote_url,
            "auto_commit": str(auto_commit).lower(),
            "auto_push": str(auto_push).lower(),
            "schedule_time": schedule_time,
            "commit_message": commit_message,
        })
    return {
        "name": name,
        "path": folder,
        "remote_url": remote_url,
        "auto_commit": auto_commit,
        "auto_push": auto_push,
        "schedule_time": schedule_time,
        "commit_message": commit_message,
    }


def load_repositories(
    csv_file: str | Path = DEFAULT_CSV,
) -> list[dict[str, str | bool]]:
    csv_path = Path(csv_file)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(CSV_COLUMNS):
            raise ValueError(
                "CSV header must be: " + ",".join(CSV_COLUMNS)
            )
        repositories: list[dict[str, str | bool]] = []
        for line_number, row in enumerate(reader, start=2):
            values = {column: (row[column] or "").strip() for column in CSV_COLUMNS}
            if not any(values.values()):
                continue
            if not all(values.values()):
                raise ValueError(f"All columns are required on CSV line {line_number}.")
            if values["auto_commit"].lower() not in {"true", "false"}:
                raise ValueError(f"Invalid auto_commit on CSV line {line_number}.")
            if values["auto_push"].lower() not in {"true", "false"}:
                raise ValueError(f"Invalid auto_push on CSV line {line_number}.")
            if not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", values["schedule_time"]
            ):
                raise ValueError(f"Invalid schedule_time on CSV line {line_number}.")
            repositories.append({
                "name": values["name"],
                "path": values["path"],
                "remote_url": values["remote_url"],
                "auto_commit": values["auto_commit"].lower() == "true",
                "auto_push": values["auto_push"].lower() == "true",
                "schedule_time": values["schedule_time"],
                "commit_message": values["commit_message"],
            })
        return repositories


def validate_repository(repository: Repository) -> Path:
    path = Path(repository).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Repository folder does not exist: {path}")
    top_level = _run_git(
        path,
        "rev-parse",
        "--show-toplevel",
        check=False,
    )
    if top_level.returncode != 0:
        raise ValueError(f"Not a valid Git repository: {path}")
    repository_root = Path(top_level.stdout.strip()).resolve()
    if os.path.normcase(str(repository_root)) != os.path.normcase(str(path)):
        raise ValueError(f"Not a valid Git repository: {path}")
    return path


def initialize_repository(repository: Repository) -> Path:
    """Initialize a normal existing folder as a main-branch Git repository."""
    path = Path(repository).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Repository folder does not exist: {path}")

    top_level = _run_git(
        path,
        "rev-parse",
        "--show-toplevel",
        check=False,
    )
    is_repository_root = (
        top_level.returncode == 0
        and os.path.normcase(str(Path(top_level.stdout.strip()).resolve()))
        == os.path.normcase(str(path))
    )
    if not is_repository_root:
        _run_git(path, "init", "-b", "main")
        print(f"Initialized Git repository in {path}.")
    return validate_repository(path)


def get_changes(repository: Repository) -> dict[str, list[str]]:
    path = validate_repository(repository)
    modified: set[str] = set()
    untracked: set[str] = set()
    deleted: set[str] = set()

    result = _run_git(
        path,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    records = result.stdout.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        if not record:
            index += 1
            continue
        status = record[:2]
        changed_path = record[3:]
        if "R" in status or "C" in status:
            index += 1
        if status == "??":
            untracked.add(changed_path)
        elif "D" in status:
            deleted.add(changed_path)
        else:
            modified.add(changed_path)
        index += 1

    return {
        "modified": sorted(modified - deleted),
        "untracked": sorted(untracked),
        "deleted": sorted(deleted),
    }


def stage_files(repository: Repository, files: list[str]) -> list[str]:
    path = validate_repository(repository)
    selected = list(dict.fromkeys(files))
    if not selected:
        return []
    _run_git(path, "add", "-A", "--", *selected)
    return selected


def commit_changes(repository: Repository, message: str) -> CommitResult | None:
    path = validate_repository(repository)
    if not message.strip():
        raise ValueError("Commit message cannot be empty.")

    staged = _run_git(
        path,
        "diff",
        "--cached",
        "--quiet",
        "--exit-code",
        check=False,
    )
    if staged.returncode == 0:
        return None
    if staged.returncode != 1:
        raise ValueError((staged.stderr or "Could not inspect staged changes.").strip())

    _run_git(path, "commit", "-m", message.strip())
    sha = _run_git(path, "rev-parse", "HEAD").stdout.strip()
    return CommitResult(hexsha=sha, message=message.strip())


def push_changes(
    repository: Repository,
    remote_name: str = "origin",
    branch: str | None = None,
):
    path = validate_repository(repository)
    branch_name = branch or _run_git(
        path, "branch", "--show-current"
    ).stdout.strip()
    if not branch_name:
        raise ValueError("Cannot push a detached HEAD.")
    result = _run_git(
        path,
        "push",
        "--set-upstream",
        remote_name,
        f"{branch_name}:{branch_name}",
    )
    output = (result.stdout + result.stderr).strip()
    return output.splitlines() or ["Push completed."]


def pull_changes(
    repository: Repository,
    remote_name: str = "origin",
    branch: str | None = None,
):
    path = validate_repository(repository)
    branch_name = branch or _run_git(
        path, "branch", "--show-current"
    ).stdout.strip()
    if not branch_name:
        raise ValueError("Cannot pull into a detached HEAD.")
    result = _run_git(path, "pull", "--rebase", remote_name, branch_name)
    output = (result.stdout + result.stderr).strip()
    return output.splitlines() or ["Pull completed."]


def get_commit_history(
    repository: Repository,
    max_count: int = 10,
) -> list[dict[str, Any]]:
    path = validate_repository(repository)
    result = _run_git(
        path,
        "log",
        f"--max-count={max_count}",
        "--format=%H%x1f%s%x1f%an%x1f%ae%x1f%cI%x1e",
    )
    history: list[dict[str, Any]] = []
    for record in result.stdout.strip("\x1e\n").split("\x1e"):
        if not record.strip():
            continue
        values = record.strip().split("\x1f")
        if len(values) != 5:
            continue
        history.append({
            "hexsha": values[0],
            "message": values[1],
            "author": values[2],
            "author_email": values[3],
            "committed_datetime": datetime.fromisoformat(values[4]),
        })
    return history


def remove_repository(
    name: str,
    csv_file: str | Path = DEFAULT_CSV,
) -> bool:
    csv_path = Path(csv_file)
    repositories = load_repositories(csv_path)
    target = name.strip().casefold()
    remaining = [
        item
        for item in repositories
        if str(item["name"]).casefold() != target
    ]
    if len(remaining) == len(repositories):
        return False

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for item in remaining:
            writer.writerow({
                **item,
                "auto_commit": str(item["auto_commit"]).lower(),
                "auto_push": str(item["auto_push"]).lower(),
            })
    return True


def auto_commit(
    repository: Repository | dict[str, str | bool],
    message: str | None = None,
    files: list[str] | None = None,
    remote_name: str = "origin",
    pull_first: bool = False,
    push: bool | None = None,
):
    if isinstance(repository, dict):
        if not bool(repository["auto_commit"]):
            return None
        repo_source: Repository = str(repository["path"])
        message = message or str(repository["commit_message"])
        should_push = bool(repository["auto_push"]) if push is None else push
    else:
        repo_source = repository
        should_push = True if push is None else push
    if not message or not message.strip():
        raise ValueError("A commit message is required.")

    repo = validate_repository(repo_source)

    changes = get_changes(repo)
    all_changed = changes["modified"] + changes["untracked"] + changes["deleted"]
    selected = all_changed if files is None else files
    if not selected:
        if should_push:
            if pull_first:
                pull_changes(repo, remote_name)
            push_changes(repo, remote_name)
        return None

    stage_files(repo, selected)
    commit = commit_changes(repo, message)
    if commit is not None and should_push:
        if pull_first:
            pull_changes(repo, remote_name)
        push_changes(repo, remote_name)
    return commit


def get_repo_status(repository: Repository) -> dict[str, Any]:
    path = validate_repository(repository)
    changes = get_changes(path)
    return {
        "branch": _run_git(path, "branch", "--show-current").stdout.strip(),
        "is_dirty": any(changes.values()),
        "changes": changes,
    }


def load_git_users(
    csv_file: str | Path = GIT_USERS_CSV,
) -> list[dict[str, str]]:
    csv_path = Path(csv_file)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(GIT_USER_COLUMNS):
            raise ValueError("Git user CSV header must be: " + ",".join(GIT_USER_COLUMNS))
        return [
            {column: (row[column] or "").strip() for column in GIT_USER_COLUMNS}
            for row in reader
            if all((row[column] or "").strip() for column in GIT_USER_COLUMNS)
        ]


def add_git_user(
    profile_name: str,
    git_name: str,
    git_email: str,
    github_username: str,
    csv_file: str | Path = GIT_USERS_CSV,
    authenticate: bool = False,
) -> dict[str, str]:
    user = {
        "profile_name": profile_name.strip(),
        "git_name": git_name.strip(),
        "git_email": git_email.strip(),
        "github_username": github_username.strip(),
    }
    if not all(user.values()):
        raise ValueError("All Git user fields are required.")
    if "@" not in user["git_email"]:
        raise ValueError("Enter a valid Git email address.")

    users = load_git_users(csv_file)
    if any(
        item["profile_name"].casefold() == user["profile_name"].casefold()
        for item in users
    ):
        raise ValueError(f"Git user profile already exists: {user['profile_name']}")
    if authenticate:
        _login_github_account(user["github_username"])

    csv_path = Path(csv_file)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GIT_USER_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(user)
    return user


def get_current_git_user(repository: Repository) -> dict[str, str]:
    path = validate_repository(repository)
    git_name = _run_git(
        path, "config", "--get", "user.name", check=False
    ).stdout.strip()
    git_email = _run_git(
        path, "config", "--get", "user.email", check=False
    ).stdout.strip()
    github_username = _run_git(
        path,
        "config",
        "--get",
        "credential.https://github.com.username",
        check=False,
    ).stdout.strip()
    accounts = _authenticated_github_accounts()
    if not github_username and len(accounts) == 1:
        github_username = accounts[0]
    return {
        "git_name": git_name,
        "git_email": git_email,
        "github_username": github_username,
        "github_authenticated": (
            "yes"
            if github_username.casefold()
            in {account.casefold() for account in accounts}
            else "no"
        ),
        "authenticated_accounts": ", ".join(accounts),
    }


def switch_git_user(
    repository: Repository,
    user: dict[str, str],
) -> dict[str, str]:
    missing = [column for column in GIT_USER_COLUMNS if not user.get(column)]
    if missing:
        raise ValueError("Git user profile is missing: " + ", ".join(missing))

    path = validate_repository(repository)
    _login_github_account(user["github_username"])
    _run_git(path, "config", "--local", "user.name", user["git_name"])
    _run_git(path, "config", "--local", "user.email", user["git_email"])
    _run_git(
        path,
        "config",
        "--local",
        "credential.https://github.com.username",
        user["github_username"],
    )
    return get_current_git_user(path)


def main() -> int:
    menu = """
GitCommit
1. List repositories
2. Add repository
3. Remove repository
4. Show repository status
5. Pull repository
6. Commit repository changes
7. Push repository
8. Show commit history
9. Run enabled auto-commits now
10. Show current Git user
11. Add Git user profile
12. Switch Git user
0. Exit
"""

    while True:
        print(menu)
        try:
            choice = input("Select an option: ").strip()

            if choice == "0":
                print("Goodbye.")
                return 0

            repositories = load_repositories()

            if choice == "1":
                if not repositories:
                    print("No repositories are saved.")
                    continue
                for number, item in enumerate(repositories, start=1):
                    print(
                        f"{number}. {item['name']} | {item['path']} | "
                        f"commit={item['auto_commit']} | push={item['auto_push']} | "
                        f"time={item['schedule_time']}"
                    )
                continue

            if choice == "2":
                name = input("Project name: ").strip()
                path = input("Local repository path: ").strip().strip('"')
                remote_url = input("GitHub remote URL: ").strip()
                auto_commit_value = input("Enable auto commit? [y/N]: ").strip().lower()
                auto_push_value = input("Enable auto push? [y/N]: ").strip().lower()
                schedule_time = input("Daily schedule time (HH:MM): ").strip()
                commit_message = input("Default commit message: ").strip()

                repo_path = initialize_repository(path)
                origin = _run_git(
                    repo_path,
                    "remote",
                    "get-url",
                    "origin",
                    check=False,
                )
                if origin.returncode == 0:
                    _run_git(repo_path, "remote", "set-url", "origin", remote_url)
                else:
                    _run_git(repo_path, "remote", "add", "origin", remote_url)

                item = add_repository(
                    name=name,
                    path=path,
                    remote_url=remote_url,
                    auto_commit=auto_commit_value in {"y", "yes", "true", "1"},
                    auto_push=auto_push_value in {"y", "yes", "true", "1"},
                    schedule_time=schedule_time,
                    commit_message=commit_message,
                )
                print(f"Saved {item['name']}.")
                commit_item = {
                    **item,
                    "auto_commit": True,
                    "auto_push": False,
                }
                commit = auto_commit(commit_item)
                push_results = push_changes(path)
                if commit is None:
                    print("No matching file changes to commit.")
                else:
                    print(f"Created commit {commit.hexsha[:8]}.")
                print(f"Initial push completed ({len(push_results)} result(s)).")
                continue

            if choice == "3":
                name = input("Project name to remove: ").strip()
                print(
                    f"Removed {name}."
                    if remove_repository(name)
                    else f"Repository not found: {name}"
                )
                continue

            if choice == "9":
                enabled = [item for item in repositories if item["auto_commit"]]
                if not enabled:
                    print("No repositories have auto_commit enabled.")
                    continue
                for item in enabled:
                    try:
                        commit = auto_commit(item, pull_first=True)
                        if commit is None:
                            print(f"{item['name']}: no changes.")
                        else:
                            action = "committed and pushed" if item["auto_push"] else "committed"
                            print(f"{item['name']}: {action} {commit.hexsha[:8]}.")
                    except (OSError, ValueError) as exc:
                        print(f"{item['name']}: failed: {exc}")
                continue

            if choice == "11":
                profile_name = input("Profile name: ").strip()
                git_name = input("Git commit name: ").strip()
                git_email = input("Git commit email: ").strip()
                github_username = input("GitHub username: ").strip()
                user = add_git_user(
                    profile_name,
                    git_name,
                    git_email,
                    github_username,
                    authenticate=True,
                )
                print(
                    f"Saved and authenticated Git user profile "
                    f"{user['profile_name']}."
                )
                continue

            if choice not in {"4", "5", "6", "7", "8", "10", "12"}:
                print("Invalid option.")
                continue
            if not repositories:
                print("No repositories are saved. Add one first.")
                continue

            for number, item in enumerate(repositories, start=1):
                print(f"{number}. {item['name']} ({item['path']})")
            selected_number = int(input("Repository number: ").strip())
            if not 1 <= selected_number <= len(repositories):
                raise ValueError("Repository number is out of range.")
            selected = repositories[selected_number - 1]
            selected_path = str(selected["path"])

            if choice == "4":
                status = get_repo_status(selected_path)
                print(f"Branch: {status['branch']}")
                print(f"Working tree dirty: {status['is_dirty']}")
                for category, paths in status["changes"].items():
                    print(f"{category}: {', '.join(paths) if paths else 'none'}")

            elif choice == "5":
                results = pull_changes(selected_path)
                print(f"Pull completed ({len(results)} result(s)).")

            elif choice == "6":
                changes = get_changes(selected_path)
                available = (
                    changes["modified"] + changes["untracked"] + changes["deleted"]
                )
                if not available:
                    print("No changes to commit.")
                    continue
                for number, path in enumerate(available, start=1):
                    print(f"{number}. {path}")
                selection = input(
                    "File numbers separated by commas, or press Enter for all: "
                ).strip()
                if selection:
                    indexes = {
                        int(value.strip())
                        for value in selection.split(",")
                        if value.strip()
                    }
                    if not indexes or any(
                        index < 1 or index > len(available) for index in indexes
                    ):
                        raise ValueError("One or more file numbers are invalid.")
                    files = [
                        path
                        for number, path in enumerate(available, start=1)
                        if number in indexes
                    ]
                else:
                    files = available
                message = input(
                    f"Commit message [{selected['commit_message']}]: "
                ).strip() or str(selected["commit_message"])
                push_answer = input(
                    f"Push after commit? [{'Y/n' if selected['auto_push'] else 'y/N'}]: "
                ).strip().lower()
                should_push = (
                    bool(selected["auto_push"])
                    if not push_answer
                    else push_answer in {"y", "yes", "true", "1"}
                )
                commit = auto_commit(
                    selected_path,
                    message,
                    files=files,
                    push=should_push,
                )
                if commit is not None:
                    print(f"Created commit {commit.hexsha[:8]}.")

            elif choice == "7":
                results = push_changes(selected_path)
                print(f"Push completed ({len(results)} result(s)).")

            elif choice == "8":
                count_text = input("Number of commits [10]: ").strip()
                count = int(count_text) if count_text else 10
                if count < 1:
                    raise ValueError("Commit count must be at least 1.")
                history = get_commit_history(selected_path, count)
                for commit in history:
                    print(
                        f"{commit['hexsha'][:8]} | "
                        f"{commit['committed_datetime']:%Y-%m-%d %H:%M} | "
                        f"{commit['author']} | {commit['message']}"
                    )

            elif choice == "10":
                user = get_current_git_user(selected_path)
                print(f"Git name: {user['git_name'] or 'not configured'}")
                print(f"Git email: {user['git_email'] or 'not configured'}")
                print(
                    "GitHub username: "
                    f"{user['github_username'] or 'not configured'}"
                )
                print(f"Authenticated: {user['github_authenticated']}")
                print(
                    "Accounts in Git Credential Manager: "
                    f"{user['authenticated_accounts'] or 'none'}"
                )

            elif choice == "12":
                users = load_git_users()
                if not users:
                    print("No Git user profiles are saved. Use option 11 first.")
                    continue
                for number, user in enumerate(users, start=1):
                    print(
                        f"{number}. {user['profile_name']} | "
                        f"{user['git_name']} <{user['git_email']}> | "
                        f"GitHub: {user['github_username']}"
                    )
                user_number = int(input("Git user number: ").strip())
                if not 1 <= user_number <= len(users):
                    raise ValueError("Git user number is out of range.")
                active = switch_git_user(selected_path, users[user_number - 1])
                print(
                    f"Switched {selected['name']} to "
                    f"{active['git_name']} <{active['git_email']}> "
                    f"(GitHub: {active['github_username']})."
                )

        except (OSError, ValueError) as exc:
            print(f"Error: {exc}")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0


if __name__ == "__main__":
    from gitcommit_gui import run_gui

    raise SystemExit(run_gui())
