# Supabase sikker opsætning (FamilBudget)

## 1) Opret lokal `.env`

1. Kopiér [.env.example](C:/Users/Shawn/Desktop/software/.env.example) til `.env`.
2. Udfyld værdier:

```env
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=eyJ...
SUPABASE_SECRET_KEY=sb_secret_...
SUPABASE_JWKS_URL=https://YOUR_PROJECT.supabase.co/auth/v1/.well-known/jwks.json
```

> `.env` er ignoreret i Git via [.gitignore](C:/Users/Shawn/Desktop/software/.gitignore).

## 2) Forbind appen sikkert

- Desktop-app må kun bruge:
  - `SUPABASE_URL`
  - `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY` må kun bruges til:
  - migrations
  - backend scripts
  - admin-værktøjer
- `SUPABASE_JWKS_URL` bruges til server-side JWT-verificering

Konfiguration læses i [config.py](C:/Users/Shawn/Desktop/software/config.py).
Hvis en påkrævet variabel mangler, kastes en tydelig `ConfigError`.

## 3) Supabase key rotation (anbefalet flow)

1. Opret ny publishable key i Supabase.
2. Opdater:
   - lokal `.env`
   - GitHub Secrets (`SUPABASE_PUBLISHABLE_KEY`)
3. Deploy/udrul klienter.
4. Deaktiver gammel publishable key.
5. Opret ny secret key.
6. Opdater kun backend/migrations secrets.
7. Deaktiver gammel secret key.

## 4) GitHub Secrets

Sæt følgende i repository secrets:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`
- `SUPABASE_JWKS_URL`

### Eksempel brug i GitHub Actions

```yaml
env:
  SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
  SUPABASE_PUBLISHABLE_KEY: ${{ secrets.SUPABASE_PUBLISHABLE_KEY }}
  SUPABASE_SECRET_KEY: ${{ secrets.SUPABASE_SECRET_KEY }}
```

> Brug kun `SUPABASE_SECRET_KEY` i jobs der kører migrations/admin-opgaver.
