# Fotbal · živě · predikce

Mobilní PWA v češtině. Živé skóre bere prohlížeč ze tří zdrojů, předzápasová 1X2 je Dixon-Coles + Elo + LightGBM. Nasazení: GitHub Pages.

Veřejná adresa: https://robertzechovsky639-ui.github.io/fotbal-predikce-ml/

## Spuštění

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python3 scripts/download_data.py
python3 backend/train.py
python3 scripts/export_static.py
python3 -m http.server -d dist 8765
```

Testy: `python3 -m pytest tests` a `node tests/test_live.js`.

## Model

Chronologický průchod od 1993. Elo s domácí výhodou, K podle rozdílu gólů a 25% regresí k síle soutěže mezi sezónami (Evropa 1. července, Jižní Amerika, J1, Čína a MLS 1. ledna). Dixon-Coles se fituje po ligách jen z zápasů přísně před datem řezu. LightGBM je druhá vrstva na 1X2. Publikovaná pravděpodobnost je směs; váha se vybírá na posledních 120 dnech tréninku, ne na testu.

Kurzy do příznaků jdou jen předzápasové (B365H, ne B365CH). Soubory `football-data.co.uk/new` mají jen closing ceny, ty se nepoužijí. ClubElo API nešlo stáhnout (502 / timeout) a stránka s datem je aktuální žebříček, ne historie, takže rating je vlastní Elo.

Holdout je od 2025-07-01. Čísla níže jsou kandidát natrénovaný jen do tohoto data. Když brána projde, ostrý model se dofituje na všech datech; stromy se mezi dny nemění. Export jen přehrává dohrané zápasy do Elo (`state.json`, okno 21 dní, stejné id jen jednou).

Brána: log loss aspoň o 0,01 lepší než frekvence, RPS aspoň o 0,003, a směs nesmí být horší než Elo o víc než 0,001. Když neprojde a release už existuje, zůstane předchozí `gbm.txt` a `dc.json`.

### Test od 2025-07-01

| Model | N | Přesnost | Log loss | RPS |
|---|---:|---:|---:|---:|
| Směs (váha LightGBM 1,0) | 19451 | 50,0 % | 1,0130 | 0,2070 |
| LightGBM | 19451 | 50,0 % | 1,0130 | 0,2070 |
| Elo + Poisson | 19451 | 48,5 % | 1,0296 | 0,2122 |
| Frekvence (baseline) | 19451 | 44,3 % | 1,0720 | 0,2271 |
| Dixon-Coles (jen ligy s modelem) | 15568 | 47,4 % | 1,0365 | 0,2139 |

Reprezentace (jen Elo, jiný žebříček): n = 1396, přesnost 57,1 %, log loss 0,940, RPS 0,192 proti frekvenci 1,051 / 0,231.

### Podle regionu (směs na stejném holdoutu)

| Region | N | Přesnost | Log loss | RPS | Elo log loss |
|---|---:|---:|---:|---:|---:|
| Evropa nejvyšší | 2862 | 53,5 % | 0,971 | 0,194 | 1,000 |
| Evropa nižší | 12167 | 49,3 % | 1,018 | 0,208 | 1,037 |
| Česko | 71 | 53,5 % | 1,004 | 0,211 | 0,993 |
| Evropské poháry | 619 | 53,0 % | 1,002 | 0,222 | 1,007 |
| Asie | 598 | 49,8 % | 1,023 | 0,209 | 1,019 |
| Jižní Amerika | 1993 | 48,3 % | 1,029 | 0,210 | 1,034 |
| Ostatní | 1141 | 50,0 % | 1,038 | 0,216 | 1,040 |

Český holdout je krátký (openfootball má Chance ligu souvisle až od 2018 a formát 2026/27 se čte zvlášť). Na těch 71 zápasech je Elo o trochu přesnější než směs; v aplikaci dostanou zápasy s málo historií pořád 1X2 z Elo a prioru soutěže a štítek nižší jistoty.

### Pokrytí historie

| Region | Zápasů | Lig | Od | Do |
|---|---:|---:|---|---|
| Evropa nejvyšší | 78865 | 7 | 1993-07-23 | 2026-10-19 |
| Evropa nižší | 230586 | 181 | 1993-07-28 | 2026-10-19 |
| Česko | 1515 | 3 | 2018-07-20 | 2026-09-20 |
| Evropské poháry | 4244 | 3 | 2011-09-13 | 2026-05-30 |
| Asie | 10700 | 28 | 2012-03-10 | 2026-10-18 |
| Jižní Amerika | 24007 | 36 | 2012-01-24 | 2027-12-23 |
| Reprezentace | 31197 | 156 | 1993-01-01 | 2026-10-06 |
| Ostatní | 18859 | 34 | 2010-07-17 | 2026-10-19 |

Konec u Jižní Ameriky je nejzazší datum v openfootball, včetně jednoho řádku až v roce 2027.

Asie bere J1, čínskou Super League (football-data extra), A-League, saúdskou ligu 2024/25 (openfootball) a další asijské soubory. K League nemá čistý historický CSV (football-data kód KOR přesměruje na Norsko a zahodí se); zápas dostane prioru ligy a nižší jistotu, dokud se výsledky nenaberou ze živých zdrojů do `state.json`. Stejně se chovají soutěže pod 200 zápasů nebo tým s méně než 8 zápasy.

## Živé skóre

Prohlížeč se ptá sám (CORS `*`):

- Sofascore `api.sofascore1.com/api/v1/sport/football/events/live` a u zápasů na obrazovce `/event/{id}`, `/incidents` a `/odds/1/featured`
- 365scores allscores `sports=1`, časová zóna Europe/Prague
- ESPN scoreboard po ligách, po pěti za tik

Celý Sofascore seznam (`events/live`) jde na počítači jednou za 20 s a na telefonu za 30 s. Skóre zápasů na obrazovce bere `/event/{id}`. 365scores 2,5 s / 5 s, ESPN 4 s / 8 s, začátky rozložené. JSON se čte ve workeru. `matches.json` se znovu stáhne každých 7 minut a nesmí přepsat živé skóre. Při chybě se interval zdvojnásobí až na 30 s a na pozadí je nejméně 15 s. Selže-li jeden zdroj, další dva dál posouvají stejný zápas. Skóre, minuta, červené karty ani predikce se nevrací zpět, ani když odpověď dorazí pozdě. Karty se překreslí na místě.

1X2 je po 90 minutách. Prodloužení a penalty se do gólů predikce nepočítají (`normaltime` u Sofascore, perioda u ESPN). Odložený zápas nepřepíše živý. Naplánované skóre −1 u 365scores není 0:0.

## Nasazení

`learn.yml` denně ve 02:30 UTC stáhne data, přetrénuje a nahraje release `model` jen když brána projde. `pages.yml` jede po pushi na `main`, cronem `*/10` a po 8 minutách se samo spustí znovu, když GitHub cron vynechá (`cancel-in-progress: false`). Export release nepřepisuje. Stránky musí být zapnuté jako GitHub Actions (Settings → Pages → Build and deployment → GitHub Actions).
