# KRiT2026-P4

Programowalna platforma pomiarowa **Wedge 100BF-65X (Intel Tofino-1)** —
kod P4 i skrypty kontrolne towarzyszące artykułowi:

> **Tofino jako platforma pomiarowa: nanosekundowa analiza opóźnień ruchu w sieci**
> KRiT 2026 (zgłoszenie), P. Rekosz, M. Zmuda, J. Grzelski, Ł. Jalowski, M. Żal.

## Zakres

Repozytorium zawiera **kompletny stos pomiarowy** dla dwóch układów Tofino:

### Tofino #1 — analizator (pomiarowy, Wedge 100BF-65X)

- `analyzer/p4/measurement.p4` — kod P4: agregacja portów serwera na łącza do DUT,
  rozproszenie ruchu powrotnego, stamping znaczników czasu, obliczanie
  $t_\text{out}$, statystyki SALU, histogram 128 przedziałów, **automatyczna
  kalibracja online** przez ścieżkę baseline (recyrkulacja lub pętla DAC).
- `analyzer/controller/` — skrypty BF-RT: programowanie tabel routingu i histogramu,
  polling rejestrów, korekta $t_\text{DUT} = t_\text{out} - t_\text{base}$.

### Tofino #2 — urządzenie badane (DUT, Wedge 100BF-32X)

Trzy programy P4 o rosnącej złożoności (`dut/`):

| Program | Logika | Cel pomiarowy |
|---|---|---|
| `null_switch` | tablica `forward` (port → port) | odniesienie — sam potok |
| `l2l3_switch` | `mac_lookup` + `ipv4_lookup` + TTL | typowy DC switch |
| `l2l3_recirc2` | jak wyżej + 2× recyrkulacja każdego pakietu | koszt recyrkulacji |

Kontrolery SDN dla każdego programu: `dut/controller/`.

### Generator ruchu (TRex)

Cztery scenariusze modulacji natężenia (`trex/scenarios/`):

| Scenariusz | Plik | Mechanizm |
|---|---|---|
| Stałe natężenie | `constant.py` | `STLTXCont` |
| Liniowy ramp | `ramp.py` | skrypt CLI z `port.update(mult=...)` |
| Skokowe / schodki | `step.py` | skrypt CLI |
| Microburst | `microburst.py` | `STLTXMultiBurst` |

Pozwala to symulować zarówno stabilny przepływ, jak i nagłe wzrosty/spadki
natężenia oraz microbursty charakterystyczne dla obciążeń DC.

### Pozostałe

- `trex/profile_fanio.py` — historyczny profil DUT + baseline (4 strumienie
  DUT + 4 strumienie kalibracyjne).
- `simulator/` — walidacja logiczna w Intel Tofino Model.
- `docs/` — metodyka pomiaru, mapowanie portów, recirc vs DAC.

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
python3 analyzer/controller/main.py

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
  author    = {Rekosz, Paulina and Zmuda, Marek and Grzelski, Jakub and Jalowski, Łukasz and Żal, Mariusz},
  title     = {Tofino jako platforma pomiarowa: nanosekundowa analiza opóźnień ruchu w sieci},
  booktitle = {Submitted to KRiT 2026},
  year      = {2026},
  note      = {Under review}
}
```
