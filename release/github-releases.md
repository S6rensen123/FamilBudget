# GitHub Releases til FamilBudget

## 1. Forbered release
- Opdater `version.json` med den ønskede version
- Sørg for at `budget.exe` og `budget.db` er tilgængelige i projektmappen
- Kør byggescriptet:
  `python release/build_release.py`

## 2. Hvad scriptet laver
Scriptet opretter en pakke under `release/artifacts/` med:
- `FamilBudget-v<version>/budget.exe`
- `FamilBudget-v<version>/budget.db`
- `FamilBudget-v<version>/version.json`
- `FamilBudget-v<version>/RELEASE_NOTES.md`
- `FamilBudget-v<version>.zip`

## 3. Opret release på GitHub
1. Gå til repositoryets faneblad "Releases"
2. Klik "Draft a new release"
3. Skriv titel: `FamilBudget v<version>`
4. Vælg eller opret tag: `v<version>`
5. Indsæt indhold fra `release/artifacts/FamilBudget-v<version>/RELEASE_NOTES.md`
6. Upload følgende assets:
   - `release/artifacts/FamilBudget-v<version>.zip`
   - `release/artifacts/FamilBudget-v<version>/budget.exe`
   - `release/artifacts/FamilBudget-v<version>/BudgetManagerSetup.exe` hvis installerfilen findes
7. Klik "Publish release"

## 4. Vigtigt for auto-opdatering
For at appens updater kan hente den nyeste version, skal release-assetet med selve programmet hedde `budget.exe`.
