# dockbay

Pojednostavljeni registar Docker slika. Veb-aplikacija u kojoj korisnici objavljuju repozitorijume slika, tagove, organizacije i pretražuju javni katalog.

## Tim


- Veljko Joksović R2 33/2026 (vjoksovic)
- Uroš Đošić R2 23/2026 (nerongerik)
- Viktor Srbljin R2 2/2026 (ddhoodie)


## Pokretanje

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py manage.py test
py manage.py runserver
```

Health provera: http://127.0.0.1:8000/health/

Testovi se pokreću i na svakom pull requestu ka `develop` (`.github/workflows/pr-develop.yml`). Lokalno i u CI aplikacija koristi SQLite jer je `UKS_TEST_DB` podrazumevano `ON`.
