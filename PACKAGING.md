# Packaging & Distribution Guide

CompTIA Linux+ (XK0-006 / V8) Study Trainer can be run directly from source, installed as a CLI tool via `pipx` / `uv`, or packaged into native installers for **Windows**, **macOS**, and **Linux** (AppImage & Flatpak).

---

## 1. Automated Multi-OS GitHub Releases

The workflow at `.github/workflows/release.yml` runs the full `unittest` suite first, then builds installers in parallel for all three operating systems:

- **Windows**: `LinuxPlusTrainer-Setup-Windows.exe` (PyInstaller + Inno Setup)
- **macOS**: `LinuxPlusTrainer-macOS.dmg` (PyInstaller `.app` bundle + `hdiutil`)
- **Linux**: `LinuxPlusTrainer-x86_64.AppImage` (PyInstaller + `appimagetool`)

### Triggering a Release

1. Push your repository to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Release v1.0.0"
   git branch -M main
   git remote add origin https://github.com/<your-user>/linux-plus-trainer.git
   git push -u origin main
   ```
2. Tag a version and push the tag to trigger the automated build and attach all installers to a GitHub Release:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. To run a test build without publishing a GitHub Release, open the **Actions** tab on GitHub and run **Release Multi-OS Installers** via **Run workflow** (`workflow_dispatch`).

---

## 2. Install as a CLI Command (`pipx` / `uv`)

`pyproject.toml` exposes the `linuxplus` console entry point:

```bash
# With uv
uv tool install .

# Or with pipx
pipx install .

# Launch
linuxplus              # Interactive selector (Terminal / Web / Desktop / Quit)
linuxplus --terminal   # Rich Terminal CLI
linuxplus --web        # Local Flask Web GUI
linuxplus --desktop    # Native Desktop Window (with browser fallback)
```

---

## 3. Local Build on CachyOS / Arch Linux

### Option A: Local PyInstaller Binary

```bash
python -m venv .venv-pack
source .venv-pack/bin/activate
pip install -r requirements-packaging.txt

# Generate PNG/ICO/ICNS icons
python packaging/scripts/generate_icons.py

# Build dist/LinuxPlusTrainer/
pyinstaller --noconfirm packaging/linux-plus-trainer.spec

# Run directly (launches Desktop Window Mode by default when frozen)
./dist/LinuxPlusTrainer/LinuxPlusTrainer
./dist/LinuxPlusTrainer/LinuxPlusTrainer --terminal
```

### Option B: Local Flatpak Build & Install

1. Install Flatpak and `flatpak-builder` on CachyOS:
   ```bash
   sudo pacman -S flatpak flatpak-builder
   flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
   flatpak install flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
   ```
2. Build and install locally (ensure offline wheel cache or network access for `rich` and `flask`):
   ```bash
   flatpak-builder --user --install --force-clean build-dir \
     packaging/flatpak/io.github.linuxplustrainer.LinuxPlusTrainer.yml
   ```
3. Launch from your application menu or run:
   ```bash
   flatpak run io.github.linuxplustrainer.LinuxPlusTrainer
   ```
