# GitCommit functions

`daily_github_commit.py` contains reusable functions that execute Git commands
directly inside Git Bash:

- `add_repository()`
- `load_repositories()`
- `validate_repository()`
- `get_changes()`
- `stage_files()`
- `commit_changes()`
- `push_changes()`
- `pull_changes()`
- `get_commit_history()`
- `remove_repository()`
- `auto_commit()`
- `get_repo_status()`

Install Git for Windows, Python 3, and the GUI dependency:

```powershell
py -3 -m pip install -r requirements.txt
```

The program locates Git Bash at `C:\Program Files\Git\bin\bash.exe`. A custom
location can be supplied through the `GIT_BASH_PATH` environment variable.

Start the PyQt6 desktop application:

```powershell
py -3 daily_github_commit.py
```

The GUI can add, list, and remove repositories; show status and history; pull,
select files to commit, push, run every enabled auto-commit immediately, show
activity logs, and manage Git/GitHub user profiles. Git operations run on
background workers so the window remains responsive.

Git user profiles are stored in `git_users.csv` with:

```csv
profile_name,git_name,git_email,github_username
```

The file does not store passwords or tokens. Adding a profile authenticates its
GitHub account through Git Credential Manager's browser login when necessary.
Switching a profile changes the selected repository's local `user.name`,
`user.email`, and the authenticated GitHub account selected for HTTPS pushes.

Import the functions into another Python program:

```python
from daily_github_commit import (
    add_repository,
    auto_commit,
    get_repo_status,
    load_repositories,
)

add_repository(
    "GitCommit",
    "C:/Users/NITIN/Documents/project",
    "https://github.com/your-name/project.git",
    True,
    True,
    "22:00",
    "Automated commit",
)

print(get_repo_status("C:/Users/NITIN/Documents/project"))

for repository in load_repositories():
    auto_commit(repository)
```

Repository records use `repositories.csv` with this header:

```csv
name,path,remote_url,auto_commit,auto_push,schedule_time,commit_message
```

`load_repositories()` converts `auto_commit` and `auto_push` to Python
booleans. `auto_commit(repository)` accepts a loaded row, uses its default
commit message, and pushes only when that row's `auto_push` value is `true`.
The `schedule_time` setting is stored in 24-hour `HH:MM` format for the caller
or scheduler to use.

When a repository is added from the GUI, GitCommit sets its
`origin` URL, commits all current changes, and performs an initial push.
If the selected existing folder is not already a Git repository, GitCommit
first initializes it with `git init -b main` through Git Bash.
