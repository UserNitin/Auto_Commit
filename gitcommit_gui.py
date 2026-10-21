from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTime, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

import daily_github_commit as backend


class WorkerSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()


class Worker(QRunnable):
    def __init__(self, function: Callable[[], Any]):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.result.emit(self.function())
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class RepositoryDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add repository")
        self.setMinimumWidth(520)
        self.name = QLineEdit()
        self.path = QLineEdit()
        self.remote = QLineEdit()
        self.auto_commit = QCheckBox()
        self.auto_push = QCheckBox()
        self.auto_commit.setChecked(True)
        self.auto_push.setChecked(True)
        self.time = QTimeEdit(QTime(21, 0))
        self.time.setDisplayFormat("HH:mm")
        self.message = QLineEdit("Automated commit")

        form = QFormLayout()
        form.addRow("Project name", self.name)
        form.addRow("Local folder", self.path)
        form.addRow("GitHub URL", self.remote)
        form.addRow("Auto commit", self.auto_commit)
        form.addRow("Auto push", self.auto_push)
        form.addRow("Schedule time", self.time)
        form.addRow("Commit message", self.message)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict[str, Any]:
        return {
            "name": self.name.text().strip(),
            "path": self.path.text().strip().strip('"'),
            "remote_url": self.remote.text().strip(),
            "auto_commit": self.auto_commit.isChecked(),
            "auto_push": self.auto_push.isChecked(),
            "schedule_time": self.time.time().toString("HH:mm"),
            "commit_message": self.message.text().strip(),
        }


class UserDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add GitHub account")
        self.setMinimumWidth(440)
        self.profile = QLineEdit()
        self.git_name = QLineEdit()
        self.git_email = QLineEdit()
        self.github_username = QLineEdit()

        form = QFormLayout()
        form.addRow("Profile name", self.profile)
        form.addRow("Commit name", self.git_name)
        form.addRow("Commit email", self.git_email)
        form.addRow("GitHub username", self.github_username)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict[str, str]:
        return {
            "profile_name": self.profile.text().strip(),
            "git_name": self.git_name.text().strip(),
            "git_email": self.git_email.text().strip(),
            "github_username": self.github_username.text().strip(),
        }


class CommitDialog(QDialog):
    def __init__(
        self,
        files: list[str],
        default_message: str,
        default_push: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Commit changes")
        self.resize(620, 480)
        self.files = QListWidget()
        for path in files:
            item = QListWidgetItem(path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.files.addItem(item)
        self.message = QLineEdit(default_message)
        self.push = QCheckBox("Push after commit")
        self.push.setChecked(default_push)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select files"))
        layout.addWidget(self.files)
        layout.addWidget(QLabel("Commit message"))
        layout.addWidget(self.message)
        layout.addWidget(self.push)
        layout.addWidget(buttons)

    def values(self) -> tuple[list[str], str, bool]:
        files = [
            self.files.item(index).text()
            for index in range(self.files.count())
            if self.files.item(index).checkState() == Qt.CheckState.Checked
        ]
        return files, self.message.text().strip(), self.push.isChecked()


class GitCommitWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitCommit")
        self.resize(1080, 720)
        self.thread_pool = QThreadPool.globalInstance()
        self.active_jobs = 0
        self.repositories: list[dict[str, str | bool]] = []
        self.users: list[dict[str, str]] = []
        self.tabs = QTabWidget()
        self.repo_table = QTableWidget()
        self.user_table = QTableWidget()
        self.log = QTextEdit()
        self.status = QLabel("Ready")
        self.action_buttons: list[QPushButton] = []
        self.setCentralWidget(self.tabs)
        self._build_repositories_tab()
        self._build_accounts_tab()
        self._build_log_tab()
        self._apply_style()
        self.refresh_all()

    def _button(self, text: str, callback: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(callback)
        self.action_buttons.append(button)
        return button

    def _build_repositories_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Repositories")
        title.setObjectName("title")
        subtitle = QLabel("Commit, synchronize, and push projects through Git Bash")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.repo_table.setColumnCount(6)
        self.repo_table.setHorizontalHeaderLabels(
            ["Name", "Local folder", "Remote", "Auto commit", "Auto push", "Time"]
        )
        self.repo_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.repo_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.repo_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.repo_table.verticalHeader().setVisible(False)
        header = self.repo_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.repo_table)

        first_row = QHBoxLayout()
        first_row.addWidget(self._button("Add", self.add_repository))
        first_row.addWidget(self._button("Remove", self.remove_repository))
        first_row.addWidget(self._button("Refresh", self.refresh_all))
        first_row.addStretch()
        first_row.addWidget(self._button("Run auto commits", self.run_auto_commits))
        layout.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.addWidget(self._button("Status", self.show_status))
        second_row.addWidget(self._button("Pull", self.pull_repository))
        second_row.addWidget(self._button("Commit", self.commit_repository))
        second_row.addWidget(self._button("Push", self.push_repository))
        second_row.addWidget(self._button("History", self.show_history))
        second_row.addStretch()
        layout.addLayout(second_row)
        layout.addWidget(self.status)
        self.tabs.addTab(page, "Repositories")

    def _build_accounts_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("GitHub accounts")
        title.setObjectName("title")
        subtitle = QLabel("Profiles use Git Credential Manager browser authentication")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.user_table.setColumnCount(4)
        self.user_table.setHorizontalHeaderLabels(
            ["Profile", "Commit name", "Commit email", "GitHub username"]
        )
        self.user_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.user_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.user_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.user_table.verticalHeader().setVisible(False)
        self.user_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.user_table)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Add account", self.add_user))
        buttons.addWidget(self._button("Show current account", self.show_current_user))
        buttons.addWidget(self._button("Switch selected account", self.switch_user))
        buttons.addStretch()
        layout.addLayout(buttons)
        self.tabs.addTab(page, "Accounts")

    def _build_log_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Activity")
        title.setObjectName("title")
        self.log.setReadOnly(True)
        layout.addWidget(title)
        layout.addWidget(self.log)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.log.clear)
        layout.addWidget(clear, alignment=Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(page, "Activity")

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #111827;
                color: #e5e7eb;
                font-family: "Segoe UI";
                font-size: 10pt;
            }
            QLabel#title {
                font-size: 22pt;
                font-weight: 700;
                color: #f9fafb;
            }
            QLabel#subtitle {
                color: #9ca3af;
                margin-bottom: 8px;
            }
            QTableWidget, QTextEdit, QListWidget, QLineEdit, QTimeEdit {
                background: #1f2937;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 5px;
                selection-background-color: #2563eb;
            }
            QHeaderView::section {
                background: #374151;
                color: #f9fafb;
                border: 0;
                padding: 8px;
                font-weight: 600;
            }
            QPushButton {
                background: #2563eb;
                color: white;
                border: 0;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #1d4ed8;
            }
            QPushButton:disabled {
                background: #4b5563;
                color: #9ca3af;
            }
            QTabBar::tab {
                background: #1f2937;
                color: #d1d5db;
                padding: 10px 18px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #2563eb;
                color: white;
            }
            QDialog {
                background: #111827;
            }
            """
        )

    def append_log(self, message: str) -> None:
        self.log.append(message)

    def set_busy(self, busy: bool, label: str = "") -> None:
        if busy:
            self.active_jobs += 1
        else:
            self.active_jobs = max(0, self.active_jobs - 1)
        disabled = self.active_jobs > 0
        for button in self.action_buttons:
            button.setDisabled(disabled)
        self.status.setText(label if disabled and label else "Ready")

    def run_task(
        self,
        label: str,
        function: Callable[[], Any],
        success: Callable[[Any], None] | None = None,
    ) -> None:
        self.append_log(label)
        self.set_busy(True, label)
        worker = Worker(function)
        worker.signals.result.connect(success or (lambda result: None))
        worker.signals.error.connect(self.show_error)
        worker.signals.finished.connect(lambda: self.set_busy(False))
        self.thread_pool.start(worker)

    def show_error(self, message: str) -> None:
        self.append_log(f"Error: {message}")
        QMessageBox.critical(self, "GitCommit", message)

    def refresh_all(self) -> None:
        try:
            self.repositories = backend.load_repositories()
            self.users = backend.load_git_users()
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.repo_table.setRowCount(len(self.repositories))
        for row, item in enumerate(self.repositories):
            values = [
                item["name"],
                item["path"],
                item["remote_url"],
                "Yes" if item["auto_commit"] else "No",
                "Yes" if item["auto_push"] else "No",
                item["schedule_time"],
            ]
            for column, value in enumerate(values):
                self.repo_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.user_table.setRowCount(len(self.users))
        for row, user in enumerate(self.users):
            values = [
                user["profile_name"],
                user["git_name"],
                user["git_email"],
                user["github_username"],
            ]
            for column, value in enumerate(values):
                self.user_table.setItem(row, column, QTableWidgetItem(value))

    def selected_repository(self) -> dict[str, str | bool] | None:
        row = self.repo_table.currentRow()
        if row < 0 or row >= len(self.repositories):
            QMessageBox.information(self, "GitCommit", "Select a repository first.")
            return None
        return self.repositories[row]

    def selected_user(self) -> dict[str, str] | None:
        row = self.user_table.currentRow()
        if row < 0 or row >= len(self.users):
            QMessageBox.information(self, "GitCommit", "Select an account first.")
            return None
        return self.users[row]

    def add_repository(self) -> None:
        dialog = RepositoryDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()

        def task() -> tuple[dict[str, str | bool], Any, list[str]]:
            path = backend.initialize_repository(values["path"])
            origin = backend._run_git(
                path, "remote", "get-url", "origin", check=False
            )
            if origin.returncode == 0:
                backend._run_git(
                    path, "remote", "set-url", "origin", values["remote_url"]
                )
            else:
                backend._run_git(
                    path, "remote", "add", "origin", values["remote_url"]
                )
            item = backend.add_repository(**values)
            initial = {**item, "auto_commit": True, "auto_push": False}
            commit = backend.auto_commit(initial)
            pushed = backend.push_changes(path)
            return item, commit, pushed

        def success(result: tuple[dict[str, str | bool], Any, list[str]]) -> None:
            item, commit, pushed = result
            detail = "no new commit" if commit is None else commit.hexsha[:8]
            self.append_log(
                f"Added {item['name']}; commit {detail}; push output {len(pushed)} line(s)"
            )
            self.refresh_all()

        self.run_task(f"Adding {values['name']}...", task, success)

    def remove_repository(self) -> None:
        item = self.selected_repository()
        if item is None:
            return
        answer = QMessageBox.question(
            self,
            "Remove repository",
            f"Remove {item['name']} from GitCommit?\nLocal files will not be deleted.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if backend.remove_repository(str(item["name"])):
            self.append_log(f"Removed {item['name']}")
            self.refresh_all()

    def show_status(self) -> None:
        item = self.selected_repository()
        if item is None:
            return

        def success(status: dict[str, Any]) -> None:
            lines = [
                f"Branch: {status['branch']}",
                f"Dirty: {'Yes' if status['is_dirty'] else 'No'}",
            ]
            for category, paths in status["changes"].items():
                lines.append(f"{category.title()}: {', '.join(paths) if paths else 'None'}")
            QMessageBox.information(self, str(item["name"]), "\n".join(lines))
            self.append_log(f"Checked status for {item['name']}")

        self.run_task(
            f"Checking {item['name']}...",
            lambda: backend.get_repo_status(str(item["path"])),
            success,
        )

    def pull_repository(self) -> None:
        item = self.selected_repository()
        if item is None:
            return
        self.run_task(
            f"Pulling {item['name']}...",
            lambda: backend.pull_changes(str(item["path"])),
            lambda result: self.append_log(
                f"Pulled {item['name']}: {' | '.join(result)}"
            ),
        )

    def push_repository(self) -> None:
        item = self.selected_repository()
        if item is None:
            return
        self.run_task(
            f"Pushing {item['name']}...",
            lambda: backend.push_changes(str(item["path"])),
            lambda result: self.append_log(
                f"Pushed {item['name']}: {' | '.join(result)}"
            ),
        )

    def commit_repository(self) -> None:
        item = self.selected_repository()
        if item is None:
            return

        def changes_ready(changes: dict[str, list[str]]) -> None:
            files = changes["modified"] + changes["untracked"] + changes["deleted"]
            if not files:
                QMessageBox.information(self, "GitCommit", "No changes to commit.")
                return
            dialog = CommitDialog(
                files,
                str(item["commit_message"]),
                bool(item["auto_push"]),
                self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            selected, message, push = dialog.values()
            if not selected:
                QMessageBox.information(self, "GitCommit", "Select at least one file.")
                return

            def success(commit: Any) -> None:
                if commit is not None:
                    self.append_log(
                        f"Committed {item['name']} as {commit.hexsha[:8]}"
                    )

            self.run_task(
                f"Committing {item['name']}...",
                lambda: backend.auto_commit(
                    str(item["path"]),
                    message,
                    files=selected,
                    push=push,
                ),
                success,
            )

        self.run_task(
            f"Loading changes for {item['name']}...",
            lambda: backend.get_changes(str(item["path"])),
            changes_ready,
        )

    def show_history(self) -> None:
        item = self.selected_repository()
        if item is None:
            return

        def success(history: list[dict[str, Any]]) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle(f"History — {item['name']}")
            dialog.resize(840, 460)
            table = QTableWidget(len(history), 4)
            table.setHorizontalHeaderLabels(["Commit", "Date", "Author", "Message"])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            for row, commit in enumerate(history):
                values = [
                    commit["hexsha"][:8],
                    commit["committed_datetime"].strftime("%Y-%m-%d %H:%M"),
                    commit["author"],
                    commit["message"],
                ]
                for column, value in enumerate(values):
                    table.setItem(row, column, QTableWidgetItem(str(value)))
            close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            close.rejected.connect(dialog.reject)
            layout = QVBoxLayout(dialog)
            layout.addWidget(table)
            layout.addWidget(close)
            dialog.exec()

        self.run_task(
            f"Loading history for {item['name']}...",
            lambda: backend.get_commit_history(str(item["path"]), 50),
            success,
        )

    def run_auto_commits(self) -> None:
        enabled = [item for item in self.repositories if item["auto_commit"]]
        if not enabled:
            QMessageBox.information(
                self, "GitCommit", "No repositories have auto commit enabled."
            )
            return

        def task() -> list[str]:
            results = []
            for item in enabled:
                try:
                    commit = backend.auto_commit(item, pull_first=True)
                    if commit is None:
                        results.append(f"{item['name']}: synchronized, no new commit")
                    else:
                        action = "committed and pushed" if item["auto_push"] else "committed"
                        results.append(
                            f"{item['name']}: {action} {commit.hexsha[:8]}"
                        )
                except Exception as exc:
                    results.append(f"{item['name']}: failed: {exc}")
            return results

        def success(results: list[str]) -> None:
            for result in results:
                self.append_log(result)
            QMessageBox.information(self, "Auto commits", "\n".join(results))

        self.run_task("Running enabled auto commits...", task, success)

    def add_user(self) -> None:
        dialog = UserDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.run_task(
            f"Authenticating {values['github_username']}...",
            lambda: backend.add_git_user(**values, authenticate=True),
            lambda user: (
                self.append_log(f"Added account {user['profile_name']}"),
                self.refresh_all(),
            ),
        )

    def show_current_user(self) -> None:
        item = self.selected_repository()
        if item is None:
            self.tabs.setCurrentIndex(0)
            return

        def success(user: dict[str, str]) -> None:
            QMessageBox.information(
                self,
                "Current account",
                "\n".join(
                    [
                        f"Repository: {item['name']}",
                        f"Commit name: {user['git_name'] or 'Not configured'}",
                        f"Commit email: {user['git_email'] or 'Not configured'}",
                        f"GitHub account: {user['github_username'] or 'Not configured'}",
                        f"Authenticated: {user['github_authenticated']}",
                        f"Known accounts: {user['authenticated_accounts'] or 'None'}",
                    ]
                ),
            )

        self.run_task(
            f"Checking account for {item['name']}...",
            lambda: backend.get_current_git_user(str(item["path"])),
            success,
        )

    def switch_user(self) -> None:
        item = self.selected_repository()
        user = self.selected_user()
        if item is None:
            self.tabs.setCurrentIndex(0)
            return
        if user is None:
            return
        self.run_task(
            f"Switching {item['name']} to {user['github_username']}...",
            lambda: backend.switch_git_user(str(item["path"]), user),
            lambda active: self.append_log(
                f"{item['name']} now uses {active['github_username']}"
            ),
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.active_jobs:
            QMessageBox.information(
                self, "GitCommit", "Wait for the active Git operation to finish."
            )
            event.ignore()
            return
        event.accept()


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GitCommit")
    window = GitCommitWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_gui())
