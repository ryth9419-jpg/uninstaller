#!/usr/bin/env python3
"""Bazzite Layer Manager: GUI for reviewing and removing rpm-ostree layered packages."""
import json
import os
import re
import sys

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QDialog, QTextEdit, QInputDialog, QProgressBar
)


def run_readonly(args):
    """Run a fixed, read-only system query; never invoke a shell."""
    try:
        import subprocess
        p = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:
        return 1, "", str(exc)


def package_inventory():
    # Prefer rpm-ostree's JSON status output so package names are not guessed
    # from the human-readable status text.
    code, stdout, stderr = run_readonly(["rpm-ostree", "status", "--json"])
    if code == 0:
        try:
            doc = json.loads(stdout)
            deployments = doc.get("deployments", [])
            if deployments:
                dep = next((d for d in deployments if d.get("booted")), deployments[0])
                packages = []
                for field, source in (
                    ("requested-packages", "Layered RPM"),
                    ("requested-local-packages", "Local RPM"),
                ):
                    values = dep.get(field, []) or []
                    for value in values:
                        # Local package entries can be structured objects on some versions.
                        if isinstance(value, str):
                            name = value
                        elif isinstance(value, dict):
                            name = value.get("name") or value.get("nevra") or value.get("package")
                        else:
                            name = str(value)
                        if name:
                            packages.append((name, source))
                # Some versions expose the same requests under package names.
                unique = []
                seen = set()
                for name, source in packages:
                    if name not in seen:
                        seen.add(name)
                        unique.append((name, source))
                return unique, None
        except (ValueError, TypeError, AttributeError) as exc:
            json_error = str(exc)
    else:
        json_error = stderr.strip() or stdout.strip() or "rpm-ostree status --json failed"

    # Conservative fallback for versions that do not provide the expected JSON fields.
    code, stdout, stderr = run_readonly(["rpm-ostree", "status"])
    if code != 0:
        return [], f"Could not read rpm-ostree status: {stderr.strip() or stdout.strip() or json_error}"
    packages = []
    for line in stdout.splitlines():
        match = re.match(r"^\s*(LayeredPackages|LocalPackages):\s*(.*)$", line)
        if not match:
            continue
        source = "Layered RPM" if match.group(1) == "LayeredPackages" else "Local RPM"
        for name in match.group(2).split():
            if name and name not in {p[0] for p in packages}:
                packages.append((name, source))
    return packages, None


class ProcessDialog(QDialog):
    """Shows command output and offers an input box if a command asks for input."""
    def __init__(self, parent, package, source):
        super().__init__(parent)
        self.setWindowTitle(f"Uninstall {package}")
        self.resize(680, 430)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"Removing request: {package}\n"
            f"Type: {source}\n\n"
            "Administrator authentication may be requested by your system. "
            "Review the output below. If the command requests typed input, enter it below."
        ))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a response only if the command asks for one")
        self.input.returnPressed.connect(self.send_input)
        row.addWidget(self.input, 1)
        send = QPushButton("Send")
        send.clicked.connect(self.send_input)
        row.addWidget(send)
        layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.close_button = QPushButton("Close")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)
        # pkexec asks the desktop's PolicyKit agent for authorization; no password is saved.
        self.process.start("pkexec", ["rpm-ostree", "uninstall", package])

    def read_output(self):
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.output.moveCursor(self.output.textCursor().MoveOperation.End)
            self.output.insertPlainText(data)
            self.output.ensureCursorVisible()

    def send_input(self):
        text = self.input.text()
        if not text:
            return
        self.process.write((text + "\n").encode("utf-8"))
        self.input.clear()

    def finished(self, exit_code, exit_status):
        self.read_output()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        if exit_code == 0:
            self.output.append("\nCommand finished successfully. The removal is staged for the next boot.")
            self.output.append("You can reboot now to apply the change, or close this window and reboot later.")
            self.progress.setFormat("Removal staged successfully")
            self.reboot_button = QPushButton("Reboot to Apply Changes")
            self.reboot_button.clicked.connect(self.request_reboot)
            self.layout().insertWidget(self.layout().count() - 1, self.reboot_button)
        else:
            self.output.append(f"\nCommand finished with exit code {exit_code}. Review the output for details.")
        self.close_button.setEnabled(True)

    def request_reboot(self):
        answer = QMessageBox.question(
            self,
            "Reboot Bazzite?",
            "Reboot now to apply the staged package removal? Save your work before continuing.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        # Ask PolicyKit for permission; no password is stored by the app.
        reboot_process = QProcess(self)
        reboot_process.start("pkexec", ["systemctl", "reboot"])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bazzite RPM Uninstaller")
        self.resize(700, 560)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        title = QLabel("Terminal-installed RPM applications")
        title.setStyleSheet("font-size: 21px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "Packages layered onto Bazzite with rpm-ostree. "
            "Choose Uninstall beside an application to remove it."
        ))

        self.list_widget = QWidget()
        self.rows = QVBoxLayout(self.list_widget)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(6)
        layout.addWidget(self.list_widget, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch(1)
        refresh = QPushButton("Refresh list")
        refresh.clicked.connect(self.refresh)
        refresh_row.addWidget(refresh)
        layout.addLayout(refresh_row)

        self.packages = []
        self.refresh()

    def clear_rows(self):
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def refresh(self):
        self.clear_rows()
        self.packages, error = package_inventory()
        if error:
            self.status.setText(error)
            return
        if not self.packages:
            self.status.setText(
                "No terminal-installed layered RPM package requests were found. "
                "This list does not include Flatpaks or apps installed inside containers."
            )
            return

        self.status.setText(
            f"{len(self.packages)} package(s) found. "
            "Uninstalling stages a system change; reboot to apply it."
        )
        for name, source in self.packages:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 6, 10, 6)
            row.setStyleSheet(
                "QWidget { background: palette(alternate-base); border-radius: 6px; }"
            )
            name_label = QLabel(name)
            name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            name_label.setToolTip(f"{name}\\n{source}")
            row_layout.addWidget(name_label, 1)
            uninstall = QPushButton("Uninstall")
            uninstall.clicked.connect(lambda checked=False, package=name, kind=source:
                                      self.uninstall_package(package, kind))
            row_layout.addWidget(uninstall)
            self.rows.addWidget(row)
        self.rows.addStretch(1)

    def uninstall_package(self, name, source):
        answer = QMessageBox.question(
            self,
            "Confirm uninstall",
            f"Do you want to uninstall this app?\\n\\n{name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        dialog = ProcessDialog(self, name, source)
        dialog.exec()
        self.refresh()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Bazzite RPM Uninstaller")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
