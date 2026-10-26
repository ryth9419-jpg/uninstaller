# Bazzite RPM Uninstaller

A basic graphical interface for relisting and removing RPM package requests layered onto a Bazzite host with `rpm-ostree`.

## Important notes

- This targets packages requested through `rpm-ostree install`, including local RPM installs where Bazzite reports them as local package requests.
- It deliberately does not offer removal of base-image packages, Flatpaks, Homebrew packages, or packages inside Toolbox/Distrobox containers.
- It uses `pkexec` so the desktop's PolicyKit authentication dialog can request administrator approval when needed. It does **not** ask you to save a sudo password inside the app.
- `rpm-ostree uninstall` usually stages a new deployment. After a successful removal, the app offers a Reboot to Apply Changes button, with a second confirmation. You can also reboot later.
- The JSON status fields can vary between rpm-ostree versions; the app includes a basic text-output fallback. Review the package list before removing anything.

## Run from source on Bazzite

Open a terminal in this folder and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install PySide6
python src/main.py
```

If your system Python does not include `venv` or `pip`, use a development container or install the Python tooling through your preferred Bazzite-supported method.

## Build an AppImage

Build on a Linux x86_64 machine. This environment does not currently have PySide6 or `appimagetool`, so the AppImage itself must be built on your Bazzite system or another compatible Linux machine.

1. Install Python 3 and `appimagetool` using your preferred trusted source.
2. Extract this project ZIP and open a terminal in the extracted folder.
3. Run:

```bash
./build-appimage.sh
```

The script installs the Python build dependencies into a local virtual environment, packages the app with PyInstaller, and creates `BazziteRPMUninstaller-x86_64.AppImage`. Test it on Bazzite before relying on it.

## Security and limitations

- The app never passes package names through a shell; it launches `pkexec` with a separate argument list.
- The output window can show command output and has a text input field. Some privileged commands do not support interactive stdin through `pkexec`; if a specific command requires a full terminal (TTY), this simple version may not be able to answer that prompt.
- This is a starter implementation. Check the source and test in a disposable system or with non-critical packages before relying on it.
