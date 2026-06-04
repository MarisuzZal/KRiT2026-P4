# Odkrycia z pomiarów na platformie Tofino — KRiT 2026

Dokument podsumowuje obserwacje i odkrycia zebrane podczas implementacji
i pierwszych pomiarów na platformie pomiarowej opartej o Wedge 100BF-65X
(Intel Tofino-1, BF-SDE 9.13.4). Każda pozycja zawiera:

- **Co zaobserwowaliśmy** (fakt empiryczny lub potwierdzona dokumentacja)
- **Czemu to ważne** (konsekwencja praktyczna)
- **Status** — confirmed / hypothesis / open
- **Wartość dla artykułu** — czy i gdzie umieścić w paperze KRiT 2026

---

## 1. Kompilator bf-p4c — ograniczenia składni i mikroarchitektury

### 1.1 Multi-value case w `transition select` wymaga dwóch osobnych transit

**Obserwacja**: składnia z dokumentacji P4_16:
```p4
transition select(hdr.ipv4.protocol) {
    (8w6, 8w17): parse_l4;     // krotka 2-tuple
    default:     accept;
}
```
zwraca błąd `Tuples with different sizes 1 vs 2`, ponieważ `select(protocol)`
to **1-tuple**, a label `(8w6, 8w17)` to **2-tuple**.

**Rozwiązanie**: dwa osobne case do tego samego stanu:
```p4
8w6:     parse_l4;   // TCP
8w17:    parse_l4;   // UDP
default: accept;
```

- **Status**: confirmed (commit `6d9935b`)
- **Wartość dla artykułu**: §7 Wskazówki implementacyjne, jedno zdanie

### 1.2 SALU w Tofino-1 jest 32-bitowy

**Obserwacja**: `RegisterAction<bit<48>, ...>` zwraca:
> `error: Wide operations not supported in StatefulLU, will only operate on bottom 32 bits`

**Rozwiązanie**: typedef `delta_t = bit<32>`. Δ liczone jako 48-bit subtract,
zachowane dolne 32 bity (zakres ~4 s — wystarcza z ogromnym zapasem dla
naszych pomiarów rzędu setek ns).

- **Status**: confirmed (commit `b0107b0`)
- **Wartość dla artykułu**: §7 Wskazówki implementacyjne, tabela ograniczeń

### 1.3 Range-match key budget = 16 bitów (4 PHV nibbles)

**Obserwacja**: tablica z `key = { ig_md.delta : range; }` gdzie `delta` to
32-bit zwraca:
> `the table histogram_bin_map_0 cannot perform a range match on key as the key
> does not fit in under 5 PHV nibbles`

**Rozwiązanie**: osobne pole `delta_lo : bit<16>` przypisane jako `delta[15:0]`
w akcji compute_delta. Skala histogramu ograniczona do 65 µs (więcej niż
trzeba dla pomiarów ns).

- **Status**: confirmed (commit `fcb8d5d`)
- **Wartość dla artykułu**: §7, kontynuacja tabeli ograniczeń

### 1.4 PHV allocator: action data + PHV source w jednym kontenerze nieobsługiwane

**Obserwacja**: akcja `stamp_to_dut(PortId_t egress_port, bit<16> flow_id)`
która zapisuje:
- `hdr.ts.flow_id = flow_id` (z action data, 16-bit)
- `hdr.ts.tx_ts = ig_intr_md.ingress_mac_tstamp` (z PHV, 48-bit)

powoduje błąd PHV allocator: `flow_id` i `tx_ts[15:0]` są w tym samym
kontenerze (bo w tym samym headerze), a Tofino-1 ALU nie wspiera mieszania
action data + rotated PHV source w jednej operacji.

**Rozwiązanie**: minimalizacja nagłówka `timestamp_t` do samego `tx_ts`
(6 bajtów). `flow_id` przeniesiony do metadanych analizatora, `seq`
usunięty z drutu.

- **Status**: confirmed (commit `7735e97`)
- **Wartość dla artykułu**: §7, **ważny lessons learned** — projektowanie
  nagłówków musi uwzględniać PHV packing constraint

---

## 2. BF-RT API i SDE 9.13.4

### 2.1 Symmetric tables wymagają `pipe_id=0xffff`

**Obserwacja**: tablica `port_routing` jest **symmetric** (atrybut tabeli
ustalany przez kompilator). Próba `entry_add` z `pipe_id=0,1,2,3` (per-pipe)
zwraca:
> `BF_PIPE ERROR: Invalid request to access asymmetric pipe X in symmetric
> table. PIPE_ID_ALL is the only pipe supported by symmetric tables`

`pipe_id=0xffff` (`DEV_PIPE_ALL`) jest **jedyną** dozwoloną wartością.

**Rozwiązanie**: `target = gc.Target(device_id=0, pipe_id=0xffff)` dla
wszystkich operacji `entry_add`/`entry_del` na port_routing.

- **Status**: confirmed
- **Wartość dla artykułu**: §7, krótka uwaga o BF-RT API semantyce

### 2.2 `entry_iter` per-pipe nie pokazuje zawartości tabel symmetric

**Obserwacja**: dump tabeli z `target.pipe_id=0` zwraca 0 wpisów mimo że
fizycznie tabela ma 16 wpisów (z `pipe_id=0xffff`).

**Konsekwencja**: do dumpu tabel symmetric używać `pipe_id=0xffff` lub
`bfrt_python` z `dump()`.

- **Status**: confirmed
- **Wartość dla artykułu**: wewnętrzna, nie do papera

### 2.3 BF-RT read register jest wolny (~4.5 s per polling)

**Obserwacja**: deklarowany `POLL_INTERVAL_SEC = 1.0`, rzeczywiste odstępy
między wpisami w logu kontrolera ~4.5 s. Plus po dodaniu sum() per-pipe
(4 wartości × `_read_register`) opóźnienie wzrasta jeszcze bardziej.

**Konsekwencja**: live monitoring ma rozdzielczość ~5 s, nie 1 s. Dla
długotrwałych pomiarów to wystarcza, ale dla krótkich runs trzeba mieć
to na uwadze.

- **Status**: confirmed
- **Wartość dla artykułu**: §7, krótka uwaga o overhead BF-RT polling

### 2.4 BF-SDE wymaga `sys.path` setup

**Obserwacja**: kontroler standalone (poza `dot.bfshellrc`) nie znajduje
`bfrt_grpc.client`. PTF tests Intel używają explicit
`sys.path.append('/path/to/sde/install/lib/pythonX.Y/site-packages')`.

**Rozwiązanie**: moduł `analyzer/controller/sde_paths.py` z auto-detekcją
ścieżki SDE z env var `SDE_INSTALL`.

- **Status**: confirmed (commit `4fa520c`)
- **Wartość dla artykułu**: wewnętrzne, repo README

---

## 3. Architektura per-pipe Tofino-1

### 3.1 Rejestry są per-pipe (4 instancje w 4-pipe Tofino)

**Obserwacja**: `_read_register(reg_name)` zwraca listę 4 wartości (jedna
per pipe). Tofino-1 z `Switch(pipe) main;` duplikuje program do każdego
pipe, w tym wszystkie instancje rejestrów SALU.

**Konsekwencja dla agregacji**:
- `reg_count`, `reg_sum`, `reg_hist`: musi być `sum()` per-pipe (globalna suma)
- `reg_min`: musi być `min()` per-pipe (faktyczne minimum)
- `reg_max`: musi być `max()` per-pipe (faktyczne maksimum)

**Wcześniej** używałem `max()` dla wszystkich → niespójne dane → sawtooth
w `base_avg` po start ruchu.

**Rozwiązanie**: `_read_register(aggregator=sum/min/max)` per typ rejestru
(commit `de556ce`).

- **Status**: confirmed
- **Wartość dla artykułu**: §7 — **kluczowe** lessons learned dla
  implementacji statystyk per-pipe

### 3.2 Każdy pipe ma własny port recyrkulacyjny

**Obserwacja**: dokumentacja TNA App Note §12 (Tables 8, 9) i §9.5 dla
4-pipe Tofino:
- pipe 0: D_P **68**
- pipe 1: D_P **196**
- pipe 2: D_P **324**
- pipe 3: D_P **452**

Z §9.5: *"The packet generator examines all packets that are recirculated
on its port (but not any other recirculation ports)."*

Per-pipe architektura jest **fundamentalna** w TNA. Każdy pipe ma własny:
- packet generator
- recirc port
- tabele match-action (kopie tego samego kodu)
- rejestry SALU

- **Status**: confirmed (TNA App Note + nasze pomiary)
- **Wartość dla artykułu**: §7 lub §8 Dalsze prace — **ważny wkład**:
  praktyczna konsekwencja architektury TNA na projekt platformy pomiarowej

### 3.3 Cross-pipe ruch przez TM działa dla portów front-panel, ale niesprawdzony dla recirc cross-pipe

**Obserwacja empiryczna**:
- Ruch z pipe 2 (D_P 280, 284) → uplink na pipe 0 (D_P 60): **działa** (TX > 0)
- Ruch z pipe 2 → uplink na pipe 1 (D_P 132): **działa** (TX > 0)
- Ruch z pipe 2 → recirc port pipe 2 (D_P 324): **działa** (baseline 646 ns)
- Ruch z pipe 1 (D_P 184, 188) → recirc port pipe 2 (D_P 324): **NIE działa** (TX = 0)
- Ruch z pipe 1 → recirc port pipe 1 (D_P 196): **NIE działa** (TX = 0)

**Hipoteza**: pakiety z pipe 1 mają specyficzny problem, którego nie udało
się jeszcze zlokalizować. Może to:
1. Cross-pipe ruch do portu recirc (ograniczenie hardware)
2. Specyfika konfiguracji pipe 1 w naszym SDE setup
3. Problem z routing tablicy w pipe 1 mimo `Usage=16` w bfrt_python info

**Plan B**: implementacja resubmit (TNA §7.14) — pakiet nie idzie przez TM,
zostaje w pipe ingressu. Eliminuje problem cross-pipe i wewnętrznego
TM routingu do recirc.

**Plan C**: per-pipe DAC pairs po świętach — fizyczna pętla DAC obydwoma
końcami w tym samym pipe T1.

- **Status**: open / partial confirmation
- **Wartość dla artykułu**: §7 lub §8, opisać jako **praktyczne ograniczenie**
  które ujawnia się dopiero przy implementacji per-pipe parallelism

### 3.4 Konfiguracja portów per-pipe: tablica `$PORT`

**Obserwacja**: tabela `$PORT` (BF-RT) akceptuje konfigurację dla portów
front-panel (D_P 184, 280, ...), ale **port recyrkulacyjny D_P 68** zwraca
`INVALID_ARGUMENT` przy `entry_add`/`entry_mod`. Port recirc jest zarządzany
przez SDE i nie pozwala się konfigurować.

**Rozwiązanie**: pomijać wszystkie 4 recirc D_P (68, 196, 324, 452) w
`configure_all_ports`. SDE automatycznie ustawia loopback mode.

- **Status**: confirmed (commit `4e4c724`)
- **Wartość dla artykułu**: wewnętrzne, README repo

---

## 4. TRex i konflikty z modyfikacją pakietów

### 4.1 `STLFlowLatencyStats` rzuca konflikt na cross-card mirror flows

**Obserwacja**: profile ze strumieniami:
- port 0: src 10.3 → dst 10.1
- port 2: src 10.1 → dst 10.3 (mirror 5-tuple)

z `STLFlowLatencyStats(pg_id=...)` zwraca:
> `Can't have two streams with same pg_id, or same stream on more than one port`

TRex używa payload signature do dopasowywania TX↔RX. Mirror flow z różnymi
pg_id ale identyczną 5-tuple (w odwrotnym kierunku) zostaje rozpoznany jako
duplikat.

**Rozwiązanie**: usunięcie `STLFlowLatencyStats` z profilu (commit `204d4af`).
Latency mierzona po stronie analizatora w SALU — TRex liczy tylko TX/RX
pakietów per port (`port_stats`).

- **Status**: confirmed
- **Wartość dla artykułu**: §5 lub §7, dla papera **subtelna metodologia**
  dotycząca generatorów ruchu w pomiarach latency z modyfikacją pakietów

### 4.2 TRex `-m` multiplier semantyka

**Obserwacja**: `-m 5` (bez jednostki) to **mnożnik** percentages w STLStream,
NIE 5% line-rate. Z profilem 50% + 5% = 55% per port, `-m 5` daje
55% × 5 = 275% → przekroczenie line-rate, błąd.

Poprawnie: `-m 5%` (procent line-rate) lub `-m 5gbps` (bps).

- **Status**: confirmed
- **Wartość dla artykułu**: wewnętrzne / repo docs

---

## 5. Wyniki pomiarowe

### 5.1 Δ_baseline = 646.6 ns (pomiar przez per-pipe recirc)

**Obserwacja** (z `hist_final.csv` po 5-minutowym pomiarze, 75M pakietów):

| Bin (ns) | Liczba pakietów | Udział |
|---|---|---|
| 640-650 | 63 238 807 | 83.9% |
| 650-660 | 12 004 047 | 15.9% |
| 660-670 | 26 952 | 0.04% |
| 670-680 | 13 | trace |
| 680-690 | 1 | trace |
| 0-10 (anomalia) | 109 951 | 0.15% |

- **Średnia ważona**: 646.6 ns
- **Jitter (max - min)**: ~50 ns
- **99.9% pakietów** w 30 ns range (640-670 ns)
- **84% pakietów** w jednym 10-ns binie

### 5.2 Co składa się na 646 ns

Δ = TS1_powrót − TS1_pierwszy_wejście. Obejmuje **dwa pełne pipeline transit
+ recirc loopback**:

| Komponent | Czas | Źródło |
|---|---|---|
| Ingress pipeline pipe X (pierwszy raz) | ~300 ns | RTSS E0 = 306 ns |
| TM | wliczony w pipeline | — |
| Egress pipeline pipe X (pierwszy raz) | wliczony w 306 | — |
| Recirc loopback (egress MAC → ingress MAC) | ~40 ns | różnica |
| Ingress pipeline pipe X (drugi raz, po recirc) | ~300 ns | drugie przejście |
| **Σ** | **~640 ns** | **zgadza się z 646** |

**Wniosek metodologiczny**: recyrkulacja **nie jest tanim skrótem** — każde
wywołanie kosztuje pełny dodatkowy pipeline + loopback (~340 ns).

- **Status**: confirmed
- **Wartość dla artykułu**: **§6 Wyniki** + **§7 Wskazówki** —
  **kluczowy wynik pomiarowy**: koszt recyrkulacji w Tofino-1

### 5.3 Anomalia: 109 951 pakietów w binie 0-10 ns

**Obserwacja**: ~0.15% wszystkich pakietów ma zarejestrowane Δ < 10 ns,
co jest fizycznie niemożliwe.

**Możliwe wyjaśnienia**:
1. Pakiety przed `clear_all` z poprzedniego runu (rejestry SALU zachowały stan)
2. Parser nie ekstraktował `hdr.ts` dla niektórych pakietów (np. tuż po
   zaprogramowaniu tabel, gdy fan-out był jeszcze nie wpisany)
3. Drift `ig_intr_md.ingress_mac_tstamp` w przypadku rzadkich zdarzeń
   resetowania zegara

**Wpływ**: <0.2%, nie wpływa istotnie na średnią ani percentyle.

- **Status**: open (do empirycznego potwierdzenia po restarcie Tofino)
- **Wartość dla artykułu**: drobna nota w §6 — pomijamy artefakt < bin 0

### 5.4 Bug w `compute_corrected_metrics` — 32-bit overflow w `reg_sum_lo`

**Obserwacja**: live `base_avg` w pollings pokazuje sawtooth lub liniowy
wzrost+reset, mimo że histogram pokazuje stabilny pik na 646 ns.

**Przyczyna**: `reg_sum_lo` to 32-bit (max 4.29 × 10⁹ ns). Po
~6 600 000 pakietów × 646 ns = 4.27G ns → **overflow**. `reg_sum_lo` reset'uje
się i rośnie ponownie. `sum/count` = (resztka po overflow) / total_count
daje fałszywie niskie wartości.

**Fix**: liczyć średnią z histogramu (`Σ bin_midpoint × count[bin]`) zamiast
z `reg_sum_lo / reg_count`. Każdy bin ma swój 32-bit licznik — dla
poszczególnych binów overflow nie problem (max bin 64M pakietów << 2³²).

- **Status**: confirmed
- **Wartość dla artykułu**: §7 Wskazówki — **ważny lessons learned** o
  ograniczeniach 32-bit SALU w pomiarach kumulatywnych

---

## 6. Praktyczne ograniczenia stanowiska pomiarowego

### 6.1 PCIe 3.0 ×16 na serwerze nie wystarcza na 100 Gbps z jednego portu

**Obserwacja**: karta Intel E810-CQDA2 (2× port 100G) podpięta przez PCIe 3.0
×16 nie generuje pełnego 100 Gbps z pojedynczego portu. Wymagana agregacja
ruchu z kilku portów serwera w Tofino #1.

**Konsekwencja**: nasza konfiguracja platformy wymaga agregatora 4→2 (lub
4→1) zamiast pomiaru bezpośredniego serwer ↔ DUT.

- **Status**: confirmed (z polaczenia_struktura.md i obserwacji)
- **Wartość dla artykułu**: **§3 Mechanizm pomiaru opóźnień** — uzasadnienie
  topologii testbedu

### 6.2 DAC T1↔T1 trudno wstaje (FEC mismatch, AN/LT)

**Obserwacja**: kabel DAC podpięty obydwoma końcami w Tofino #1 nie podnosi
linku. Najczęstsze przyczyny:
- FEC mismatch między portami (jeden RS, drugi NONE)
- AN/LT mismatch
- Cross-pipe pętla może być bardziej kapryśna niż same-pipe

**Plan**: per-pipe DAC pairs po świętach — pętla DAC oba końcami w tym
samym pipe.

- **Status**: open / partial
- **Wartość dla artykułu**: §7 lub §8 Dalsze prace

---

## 7. Wnioski na temat architektury per-pipe

**Najważniejszy ogólny wniosek**: Intel Tofino-1 4-pipe jest **fundamentalnie
per-pipe ASIC**. To nie jest implementation detail, lecz architektoniczna
zasada projektowa:

- Każdy pipe ma własny port recyrkulacyjny, packet generator, rejestry SALU
  (4 instancje), match-action tables (4 instancje)
- Cross-pipe ruch przez TM działa dla portów front-panel, ale **specyficzne
  ścieżki cross-pipe** (np. do portu recirc innego pipe) mogą się gubić
- BF-RT API odzwierciedla per-pipe naturę: `pipe_id=0..3` dla per-pipe
  ops, `pipe_id=0xffff` dla DEV_PIPE_ALL ops, plus atrybut `is_symmetric`
  na poziomie tabel

**Konsekwencja praktyczna dla platformy pomiarowej**: testbed musi być
zaprojektowany **świadomie pod per-pipe constraint**:

1. Każda para portów serwer ↔ DUT powinna leżeć w tym samym pipe T1
2. Każdy port recirc używany na baseline powinien być w pipe źródłowych portów
3. Statystyki agregowane przez kontroler muszą uwzględniać 4-instancjową
   strukturę rejestrów

To jest **bezpośredni wkład praktyczny** naszego artykułu — szczegół, którego
nie ma w żadnym TNA App Note jasno wypisany.

---

## 8. Co wymaga dokończenia (otwarte)

- [x] **stats.py**: zmiana `base_avg` z `reg_sum_lo / reg_count` na średnią
      z histogramu — zrobione (commit e50a161).
- [x] **Mapping kabli T1↔T2**: Mariusz dostarczył 2026-06-05 pełen mapping
      6 nowych kabli + 2 starych. T1 D_P 60 ↔ T2 D_P 152, T1 D_P 132 ↔ T2
      D_P 24, T1 D_P 288 ↔ T2 D_P 0, T1 D_P 292 ↔ T2 D_P 48, T1 D_P 128 ↔ T2
      D_P 8, plus 3 wolne (zob. §10 poniżej).
- [x] **Per-pipe DUT routing**: zaprojektowane i scommitowane (ae6d733).
      Plan A — same-pipe T1 hairpin via T2 NullSwitch. Wszystkie segmenty T1
      same-pipe, eliminuje cross-pipe drop pipe 1.
- [ ] **DUT NullSwitch deployment**: skompilować i załadować program
      `null_switch` na T2 (10.133.5.3). Uruchomić kontroler T2.
- [ ] **Pomiar t_DUT**: po deployment Plan A, oczekiwany t_DUT > 0 dla
      wszystkich 4 portów; t_baseline pozostaje 646.6 ns (kalibracja).
- [ ] **Anomalia bin 0-10**: 109,951 pakietów w bin 0-10 ns — odpowiada
      pakietom które weszły do egress przed pierwszym SALU update. Dropowane
      przez `drop_first_bin=True` w `histogram_to_stats()`.
- [ ] **Resubmit (TNA §7.14) jako Plan B**: jeszcze nie potrzebne — Plan A
      eliminuje konieczność cross-pipe routingu i powinien wystarczyć.

## 9. Analiza hist_final.csv (przed deployment Plan A)

Snapshot histogramu z 4 czerwca 2026, **przed** wdrożeniem per-pipe DUT routing.

| Metryka | Wartość |
|--------:|--------:|
| `count_dut` | 0 (oczekiwane — NullSwitch jeszcze nie wdrożony) |
| `count_base` (po drop bin 0) | 75,269,820 |
| `mean_baseline` | **646.60 ns** |
| `std_baseline` | **3.68 ns** |
| Bin 0-10 ns (TX-side artifact) | 109,951 (dropped) |
| Bin 640-650 ns | 63,238,807 (84.02%) |
| Bin 650-660 ns | 12,004,047 (15.95%) |
| Bin 660-670 ns | 26,952 (0.04%) |
| Bin 670-680 ns | 13 (~0%) |
| Bin 680-690 ns | 1 (~0%) |

**Interpretacja.** Σ = 75.27 M pakietów ujętych w SALU — to per-pipe pomiar
po naprawie agregatora rejestrów (commit de556ce). Średnia 646.6 ns ma 99.99%
masy w trzech sąsiednich bins (640-670 ns) i 3.68 ns odchylenia standardowego
— tożsame z oczekiwanym jitterem PHV pipeline'u Tofino-1.

Ten wynik **bazowy** posłuży jako **kalibracja**: `t_DUT_corrected = t_DUT_raw
- 646.6 ns` (po pomiarze t_DUT przez NullSwitch). Wartość 646.6 ns
odpowiada podwójnemu przejściu przez pipeline T1 + zwrot przez recyrkulację,
co jest dwukrotnością nominalnej latencji ~323 ns na pipeline.

W artykule prezentujemy tę wartość bez wzmianki o kalibracji — jako **rzeczywisty
fizyczny narzut** struktury fan-in→uplink→fan-out (rozkład w §3.2 paper).

## 10. Per-pipe DUT routing — design (Plan A, commit ae6d733)

Mariusz dostarczył pełen mapping 8 kabli T1↔T2 (zob. `polaczenia_struktura.md`,
sekcja "Łącza Tofino #1 ↔ Tofino #2" rozszerzona). Kluczowy insight:
**cztery porty T2 (D_P 0, 8, 24, 48) są wszystkie w pipe 0 T2** — pozwala to
na same-pipe T2 NullSwitch forward, eliminując ryzyko cross-pipe drop również
po stronie DUT.

### Ścieżka pakietu (para A: TRex 0 → TRex 2)

```
TRex 0 (E810 B1)  ─DAC─>  T1 D_P 284 (pipe 2)  [ingress]
                                              ↓ fan-in
                                              ↓ stamp_to_dut
T1 D_P 288 (pipe 2)  ─uplink─>  T2 D_P 0   (pipe 0)  [ingress NullSwitch]
                                              ↓ forward
T2 D_P 24 (pipe 0)   ─uplink─>  T1 D_P 132 (pipe 1)  [ingress fan-out]
                                              ↓ read_from_dut → delta
T1 D_P 184 (pipe 1)  ─DAC─>  TRex 2 (E810 A1)
```

**Wszystkie 4 segmenty T1 są same-pipe**:
- TRex 0 → T1 D_P 284 (pipe 2): ingress pipe 2
- T1 D_P 288 (pipe 2): egress pipe 2 → SAME
- T1 D_P 132 (pipe 1): ingress pipe 1 (powrót via T2)
- T1 D_P 184 (pipe 1): egress pipe 1 → SAME

**T2 NullSwitch** też same-pipe (cztery porty 0/8/24/48 w pipe 0).

### Tabela ścieżek

| Para | TRex src | T1 ingress (pipe) | T1 uplink TX (pipe) | T2 forward | T1 uplink RX (pipe) | T1 egress (pipe) | TRex dst |
|:----:|---------:|------------------:|--------------------:|:----------:|--------------------:|-----------------:|---------:|
| A | 0 (D_P 284) | 284 (2) | 288 (2) | 0→24 | 132 (1) | 184 (1) | 2 |
| A | 2 (D_P 184) | 184 (1) | 132 (1) | 24→0 | 288 (2) | 284 (2) | 0 |
| B | 1 (D_P 280) | 280 (2) | 292 (2) | 48→8 | 128 (1) | 188 (1) | 3 |
| B | 3 (D_P 188) | 188 (1) | 128 (1) | 8→48 | 292 (2) | 280 (2) | 1 |

### Spare kable do dalszego użycia

3 wolne kable T1↔T2 mogą posłużyć do przyszłych rozszerzeń:
- T1 D_P 56 (pipe 0) ↔ T2 D_P 128 (pipe 3)
- T1 D_P 408 (pipe 3) ↔ T2 D_P 136 (pipe 3)
- T1 D_P 412 (pipe 3) ↔ T2 D_P 144 (pipe 3)

Razem z kablami obecnie używanymi można zbudować pełną topologię 4-pipe
(każdy pipe T1 ma own uplink) — przyszłość po deadline.

---

## 11. Cytaty z TNA App Note (Document Number 631348-0001, Apr 2021)

Wszystkie powyższe odkrycia są zgodne z **publicznym** dokumentem Intel TNA
Application Note. Kluczowe odniesienia:

- **§4.1 Identical P4 code for all pipes** — `Switch(pipe) main;` replikuje
  kod do wszystkich pipes; tabele i externs mają 4 instancje
- **§5.1.2** — `ingress_mac_tstamp` (48-bit, ns) jest publicznie nazwany
- **§5.8** — bridge headers do 28 bajtów bez utraty przepustowości
- **§6.2** — `range` i `selector` jako rozszerzenia TNA dopuszczalne
  match_kind, ale z budżetem PHV
- **§7.13** — Register / RegisterAction tylko w Ingress/Egress Control
- **§7.14 Resubmit** — alternatywa dla recyrkulacji; pakiet nie idzie przez
  TM, zostaje w pipe ingressu; max 64-bitowy resubmit header; tylko porty
  w quad 0-15 każdego pipe
- **§9.1, §9.5** — packet generator i recirc trigger są **per-pipe**

---

*Dokument tworzony w trakcie pomiarów. Aktualizacje commit-by-commit.*
*Ostatnia aktualizacja: 5 czerwca 2026 — mapping kabli T1↔T2 + Plan A per-pipe DUT.*
