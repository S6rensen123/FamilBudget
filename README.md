# FamilBudget

[![Build Status](https://github.com/S6rensen123/FamilBudget/actions/workflows/build.yml/badge.svg)](https://github.com/S6rensen123/FamilBudget/actions/workflows/build.yml)
[![Release Status](https://github.com/S6rensen123/FamilBudget/actions/workflows/release.yml/badge.svg)](https://github.com/S6rensen123/FamilBudget/actions/workflows/release.yml)
[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)

Dansk familie- og husstandsbudget app med auto-update.

## GitHub Actions CI/CD

### CI
- Fil: `.github/workflows/ci.yml`
- OS matrix: Windows, macOS, Ubuntu
- Python matrix: 3.11, 3.12
- Kører:
  - `pip install -r requirements.txt`
  - `python -m compileall .`
  - SQLite smoke tests:
    - login tests
    - sessions tests
    - transaction tests
    - notification tests
- PR quality checks:
  - `black --check .`
  - `flake8 .`

### Build
- Fil: `.github/workflows/build.yml`
- Trigger: push til `main`, release, workflow_dispatch
- Bygger Windows `FamilBudget.exe` med PyInstaller
- Uploader artifact: `FamilBudget-Windows`

### Release
- Fil: `.github/workflows/release.yml`
- Trigger: tags `v*`
- Bygger `FamilBudget.exe`
- Opretter GitHub Release automatisk
- Uploader `FamilBudget.exe`
- Læser version fra `version.py` og viser den i release-notes
