# dockbay

Pojednostavljeni registar Docker slika. Veb-aplikacija u kojoj korisnici objavljuju repozitorijume slika, tagove, organizacije i pretražuju javni katalog.

## Tim


- Veljko Joksović R2 33/2026 (vjoksovic)
- Uroš Đošić R2 23/2026 (nerongerik)
- Viktor Srbljin R2 2/2026 (ddhoodie)


## Model

Početni dijagram klasa je u [docs/domain-model.puml](docs/domain-model.puml). Dopunjava se kako model bude rastao.

## Pokretanje

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py manage.py migrate
py manage.py test
py manage.py runserver
```

Običan nalog se pravi na http://127.0.0.1:8000/register/. Taj nalog nije administrator.

Organizacione slike se čuvaju u lokalnom `media/` direktorijumu, koji razvojni server služi samo kada je uključen `DEBUG`.

Pri prvom `migrate` nastaje nalog `superadmin`. Lozinka je u `superadmin_password.txt` u korenu projekta. Pri prvoj prijavi mora da se promeni. Dok se ne promeni, ostale stranice su zatvorene. Posle promene, samo taj nalog može da doda drugog administratora na http://127.0.0.1:8000/administrators/new/

Health provera: http://127.0.0.1:8000/health/

## Logovi

Operativni ishodi HTTP zahteva zapisuju se u `dockbay.log` u korenu projekta. Putanja se po potrebi menja promenljivom okruženja `DOCKBAY_LOG_FILE`. Elasticsearch adresa se podešava promenljivom `ELASTICSEARCH_URL` (podrazumevano `http://localhost:9200`).

Svaki red sadrži vreme, nivo, logger, metod, putanju bez query parametara i status, na primer: `2026-11-13T10:15:22+0000 INFO dockbay.requests request completed method=GET path=/health/ status=200`. `*.log` datoteke Git ignoriše.

Proces za periodično slanje novih redova u Elasticsearch mora da radi uz veb-aplikaciju: `python manage.py ship_logs`. Jedan ciklus za ručnu proveru pokreće se komandom `python manage.py ship_logs --once`. Pozicija uspešno poslatog paketa čuva se u Git-ignorisanoj checkpoint datoteci uz log.

Administratori pretražuju logove na http://127.0.0.1:8000/administrators/logs/. Upit prihvata nivoe `info`, `warning` i `error`, običnu reč, frazu u navodnicima, `word:error` za rezervisanu reč, stroge granice `before:<timezone-aware-ISO-8601>` i `after:<timezone-aware-ISO-8601>`, kao i operatore `NOT`, `AND`, `OR` i zagrade (tim redosledom prioriteta). Primer: `(warning OR error) AND "error occured"`. Vremenski primer: `error AND after:2026-11-13T10:00:00+01:00`.

Testovi se pokreću i na svakom pull requestu ka `develop` (`.github/workflows/pr-develop.yml`). Lokalno i u CI aplikacija koristi SQLite jer je `UKS_TEST_DB` podrazumevano `ON`.
