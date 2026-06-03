# KRiT2026-P4

Programowalna platforma pomiarowa **Wedge 100BF-65X (Intel Tofino-1)** —
kod P4 i skrypty kontrolne towarzyszące artykułowi:

> **Tofino jako platforma pomiarowa: nanosekundowa analiza opóźnień ruchu w sieci**
> KRiT 2026, P. Antoniewicz, M. Zaliwski, M. Sosnowski, R. Cieślak.

## Zakres

Repozytorium zawiera **kompletny stos pomiarowy**:

- `p4/measurement.p4` — kod P4 dla przełącznika pomiarowego (Tofino-1, TNA),
  realizujący równolegle: agregację 4 portów serwera na 2 uplinki do DUT,
  rozproszenie ruchu powrotnego, stamping znaczników czasu MAC, obliczanie
  Δ = t_RX − t_TX, statystyki min/max/sum/count i histogram 128 binów,
  oraz **automatyczną kalibrację online** przez ścieżkę baseline (recyrkulacja
  lub pętla DAC).

- `controller/` — skrypty Pythona (BF-RT) programujące tabele routingu i
  histogramu, odpytujące rejestry SALU, wyliczające skorygowane wartości
  Δ_DUT_real = Δ_DUT − Δ_baseline.

- `trex/` — profile TRex generujące ruch testowy (4 podsieci /16) i ruch
  kalibracyjny (10.250.0.0/16 per port serwera).

- `simulator/` — skrypty walidacyjne pod Intel Tofino Model (do rozwoju
  i testowania bez dostępu do fizycznego sprzętu).

- `docs/` — dokumentacja techniczna: metodyka pomiaru, mapowanie portów,
  porównanie wariantów baseline (recirc vs DAC).

## Środowisko docelowe

| Komponent | Wersja / model |
|---|---|
| Przełącznik pomiarowy | Edgecore Wedge 100BF-65X (Tofino-1) |
| DUT (urządzenie badane) | Edgecore Wedge 100BF-32X (Tofino-1) |
| SDE | Intel P4 Studio 9.13.2 |
| Generator ruchu | TRex v3.08 |
| Serwer | 2× Intel Xeon Cascade Lake, 2× Intel E810-CQDA2 |

## Mapowanie portów

| Rola | D_P (Tofino #1) | Podsieć / cel |
|---|---:|---|
| Serwer TRex0 (NIC#1 B1) | 284 | 10.3.0.0/16 |
| Serwer TRex1 (NIC#1 B0) | 280 | 10.2.0.0/16 |
| Serwer TRex2 (NIC#2 A1) | 184 | 10.1.0.0/16 |
| Serwer TRex3 (NIC#2 A0) | 188 | 10.0.0.0/16 |
| Uplink_A do DUT | 60 | para 10.3 ↔ 10.1 |
| Uplink_B do DUT | 132 | para 10.2 ↔ 10.0 |
| Baseline (recirc, default) | 68 (pipe 0) | 10.250.0.0/16 |
| Baseline (DAC, alternatywa) | 308 ↔ 148 | 10.250.0.0/16 |

Pełen opis: [`docs/port-mapping.md`](docs/port-mapping.md).

## Szybki start

```bash
# 1. Kompilacja kodu P4
cd p4
bf-p4c --target tofino --arch tna -o build measurement.p4

# 2. Załadowanie programu i uruchomienie kontrolera
bf_switchd --conf-file=tofino_skel.conf
python3 controller/main.py

# 3. Uruchomienie generatora ruchu (na serwerze)
trex -f trex/profile_fanio.py -m 50 -d 60
```

## Mechanizm kalibracji baseline

Znacznik czasu pobierany z wejściowego MAC obejmuje cały narzut przejścia
pakietu przez wewnętrzny potok przełącznika pomiarowego (≈ 300–400 ns,
wartość zależna od konkretnego kodu P4). Aby ten narzut wyeliminować z
wyniku, **równolegle do ruchu testowego** generowany jest strumień
kalibracyjny przepuszczany przez krótką pętlę kabla wpiętą obydwoma końcami
w przełącznik pomiarowy (wariant A — DAC zewnętrzny) lub przez port
recyrkulacyjny ASIC (wariant B — wewnętrzny). Dla każdej ścieżki utrzymywany
jest osobny komplet rejestrów statystycznych; w warstwie sterowania
wyliczana jest różnica:

```
Δ_DUT_real = Δ_DUT_zmierzone − Δ_baseline_zmierzone
```

Szczegółowa analiza: [`docs/calibration.md`](docs/calibration.md).

## Licencja

TBD (planowana: Apache 2.0)

## Cytowanie

```
@inproceedings{krit2026tofino,
  author    = {Antoniewicz, P. and Zaliwski, M. and Sosnowski, M. and Cieślak, R.},
  title     = {Tofino jako platforma pomiarowa: nanosekundowa analiza opóźnień ruchu w sieci},
  booktitle = {KRiT 2026},
  year      = {2026}
}
```
