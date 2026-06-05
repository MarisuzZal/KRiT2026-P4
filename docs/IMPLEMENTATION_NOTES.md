# Wskazówki implementacyjne — P4 dla Tofino-1

Dokument opisuje **konkretne ograniczenia** napotkane podczas implementacji
platformy pomiarowej z artykułu KRiT 2026 ("Tofino jako platforma pomiarowa:
nanosekundowa analiza opóźnień ruchu w sieci"), wraz ze sposobem ich obejścia
i odnośnikami do konkretnych commitów w tym repozytorium.

Adresowane jest do osób, które chcą reprodukować lub rozwijać tę pracę —
oraz do każdego, kto natknie się na podobne problemy pisząc kod P4
dla Intel Tofino-1 w SDE 9.13.x.

W artykule §7 (`sections/implementation.tex` w repozytorium
[`MarisuzZal/KRiT2026`](https://github.com/MarisuzZal/KRiT2026))
podaje tylko wysokopoziomowe podsumowanie tych ograniczeń —
ten dokument zawiera **techniczne detale, konkretne fragmenty kodu
i identyfikatory commitów**.

---

## Spis treści

1. [Szerokość SALU 32-bit](#1-szerokość-salu-32-bit)
2. [Klucz dopasowania zakresowego 16-bit (4 nibble PHV)](#2-klucz-dopasowania-zakresowego-16-bit-4-nibble-phv)
3. [PHV allocator dla bridge header (per-bajt alignment)](#3-phv-allocator-dla-bridge-header-per-bajt-alignment)
4. [Mieszanie action data i PHV source w jednym kontenerze](#4-mieszanie-action-data-i-phv-source-w-jednym-kontenerze)
5. [Slice bitowy z wyniku odejmowania 48-bitowego](#5-slice-bitowy-z-wyniku-odejmowania-48-bitowego)
6. [PHV per-pipe — rejestry różne między pipe'ami](#6-phv-per-pipe--rejestry-różne-między-pipeami)

---

## 1. Szerokość SALU 32-bit

**Napotkane:** Pierwotny zapis różnicy znaczników czasu jako 48-bit nie
kompilował się — bf-p4c zgłaszał `wide SALU not supported`.

```p4
// NIEDZIAŁA:
typedef bit<48> delta_t;
Register<delta_t, bit<1>>(2, ...) reg_min;
// → error: SALU operations limited to 32-bit operands
```

**Obejście:** Redukcja na 32-bit, z rzutowaniem operandów przed odejmowaniem.
Zapas 32-bit nanosekund = ok. 4.29 sekundy — dla pomiaru pojedynczych
pakietów w pełni wystarczający.

```p4
// DZIAŁA:
typedef bit<32> delta_t;
action compute_delta() {
    bit<32> hi = (bit<32>)ig_intr_md.ingress_mac_tstamp;  // dolne 32 bity
    bit<32> lo = (bit<32>)hdr.ts.tx_ts;
    ig_md.delta = hi - lo;
}
```

**Commit:** `b0107b0` — *"fix bf-p4c 'wide SALU' — delta 48-bit → 32-bit"*
**Plik:** `analyzer/p4/measurement.p4` (linie ok. 60-90)

---

## 2. Klucz dopasowania zakresowego 16-bit (4 nibble PHV)

**Napotkane:** Tabela z kluczem typu `range` w TNA może użyć kluczy
zmieszczących się w 4 nibblach PHV = 16 bitach. Próba użycia 32-bitowego
klucza zwraca `Invalid arguments` przy `entry_add`.

**Konsekwencja praktyczna:** Histogram opóźnień opartymy o tabelę
`histogram_bin_map` z kluczem `ig_md.delta[15:0] : range` może pokryć
maksymalny zakres ~65,535 ns ≈ 65 μs. Pomiary scenariuszy z recyrkulacją
(np. `l2l3_recirc2.p4` z `MAX_RECIRC=2`), gdzie Δ wynosi ok. 200 μs,
nie mieszczą się w tej tabeli.

**Obejście:** Dla pomiarów <65 μs używamy `delta[15:0]` jako klucza
range. Dla scenariuszy >65 μs polegamy na rejestrach `reg_min`/`reg_max`
(pełne 32 bity) — histogram szczegółowy pozostaje dla przyszłych prac
(jedna z opcji to przesunięcie bitowe klucza, np. `delta[19:4]` daje
zakres do 1 ms z granulacją 16 ns).

**Commits:**
- `fcb8d5d` — *"histogram range-match key bit<16> (TNA 4-nibble budget)"*
- `e59940b` — *"revert HISTOGRAM_BIN_WIDTH_NS = 20 (klucz hist_bin_map jest 16-bit)"*

**Plik:** `analyzer/p4/measurement.p4` (tabela `histogram_bin_map`)

---

## 3. PHV allocator dla bridge header (per-bajt alignment)

**Napotkane:** W programie `l2l3_recirc2.p4` zdefiniowany był nagłówek
bridge z licznikiem recyrkulacji i polem wyrównującym:

```p4
header bridge_t {
    bit<3>  recirc_count;
    bit<5>  _pad;
}
```

Akcja `recirc_inc()` jednocześnie inkrementowała licznik
(`hdr.bridge.recirc_count = ig_md.recirc_count + 1`) i zerowała pole
wyrównujące (`hdr.bridge._pad = 0`). Ze względu na to, że oba pola
mieszczą się w tym samym bajcie nagłówka, **muszą trafić do tego samego
kontenera PHV** w hardware'rze. Akcja Tofino ALU obsługuje tylko
**jeden typ instrukcji per kontener** w ramach pojedynczej akcji —
mieszanie ADD (licznik) z ASSIGN (`_pad = 0`) jest niemożliwe do syntezy.

Błąd kompilatora:
```
The following field slices must be allocated in the same container as
they are present within the same byte of header ingress::hdr.bridge:
    ingress::hdr.bridge.recirc_count
    ingress::hdr.bridge._pad
However, the program requires multiple instruction types for the same
container in the same action (SwitchIngress.recirc_inc).
```

**Obejście:** Usunięcie pola `_pad` i rozszerzenie licznika do pełnego
bajta:

```p4
header bridge_t {
    bit<8>  recirc_count;   // pełny bajt, jeden typ instrukcji
}
```

Wartość MAX_RECIRC = 2 mieści się w 8 bitach z dużym zapasem; marnujemy
5 bitów w nagłówku, ale eliminujemy konflikt w PHV.

**Commits:**
- `2c29071` — *"fix(l2l3_recirc2.p4): wreszcie usuń _pad z bridge_t"*
- `e85944c` — *"bridge.recirc_count = bit<8> (usunąć _pad)"* (pierwsza, niepełna próba)

**Plik:** `dut/p4/l2l3_recirc2.p4` (linie ok. 50-60 i 125-135)

---

## 4. Mieszanie action data i PHV source w jednym kontenerze

**Napotkane:** Pierwotny nagłówek pomiarowy miał 16 bajtów:

```p4
header timestamp_t {
    bit<48> tx_ts;       // znacznik z ingress_mac_tstamp
    bit<16> flow_id;     // identyfikator strumienia (z action params)
    bit<32> seq_value;   // numer sekwencji
    bit<32> _reserved;
}
```

Akcja `stamp_to_dut(PortId_t egress_port, bit<16> flow_id)` zapisywała
`hdr.ts.tx_ts = ig_intr_md.ingress_mac_tstamp` (PHV source) oraz
`hdr.ts.flow_id = flow_id` (action data). Po PHV allocator, oba pola
trafiały do tego samego kontenera. Tofino TNA **nie pozwala mieszać
action data z PHV source w jednym kontenerze w ramach jednej akcji**.

**Obejście:** Redukcja nagłówka do 6 bajtów (samego `tx_ts`); `flow_id`
i `seq_value` przeniesione do `ig_metadata_t` (są używane w pipeline T_P,
ale nie są transportowane na drucie, nie są potrzebne dla pakietów
wracających).

```p4
header timestamp_t {
    bit<48> tx_ts;       // tylko znacznik
}

struct ig_metadata_t {
    delta_t     delta;
    bit<1>      is_returning;
    bit<1>      path_is_baseline;
    bin_idx_t   bin;
    bit<16>     flow_id;     // ← przeniesione tutaj
    bit<32>     seq_value;   // ← przeniesione tutaj
    bit<1>      drop_flag;
}
```

**Commit:** `7735e97` — *"fix bf-p4c PHV allocator — minimal timestamp_t header"*
**Plik:** `analyzer/p4/measurement.p4` (header timestamp_t + struct ig_metadata_t)

---

## 5. Slice bitowy z wyniku odejmowania 48-bitowego

**Napotkane:** Pierwsza wersja `compute_delta` próbowała pobrać dwa
różne slice'y z 48-bitowego wyniku odejmowania:

```p4
action compute_delta() {
    ts_t diff = ig_intr_md.ingress_mac_tstamp - hdr.ts.tx_ts;  // bit<48>
    ig_md.delta    = diff[31:0];   // dolne 32 bity → SALU
    ig_md.delta_lo = diff[15:0];   // dolne 16 bitów → range key
}
```

W `context.json` po kompilacji widać że bf-p4c emit'uje **dwa
niezależne `DirectAluPrimitive sub`** zamiast jednego subtract z
dwoma slice'ami:

```json
primitive 1: DirectAluPrimitive sub
  dst: ig_md.delta       (W2 32-bit, dst_mask=0xFFFFFFFF)
  src1: ig_intr_md.ingress_mac_tstamp
  src2: hdr.ts.tx_ts

primitive 2: DirectAluPrimitive sub     ← BUG
  dst: ig_md.delta_lo    (W3 16-bit, dst_mask=0xFFFF)
  src1: ig_intr_md.ingress_mac_tstamp   ← TE SAME źródła
  src2: hdr.ts.tx_ts
```

Druga operacja sub z 48-bit operandami przez 16-bit ALU bierze
"dolne 16 bitów" z kontenera PHV — który nie jest tym samym kontenerem
co `delta[15:0]` z pierwszej operacji. Wynik: niedeterministyczny,
typowo poza zakresem klucza tabeli range-match → `NoAction` →
ig_md.bin = 0 (init) → wszystkie pakiety lądują w bin 0 histogramu.

**Obejście:** Pobrać slice z **już-obliczonego** 32-bitowego rejestru
`ig_md.delta`, nie z oryginalnego 48-bitowego odjemnika. bf-p4c
zachowuje wtedy jeden subtract i dodaje tylko extract bitów.

Plus zmieniono klucz tabeli na bezpośredni slice w kluczu (nie osobne
pole metadata):

```p4
table histogram_bin_map {
    key = { ig_md.delta[15:0] : range; }   // slice w kluczu, nie w metadata
    ...
}
```

**Commits:**
- `5a26dca` — *"fix(bug B histogram): slice w kluczu tabeli zamiast osobnego pola delta_lo"*
- `701fbb2` — *"diag(Bug B): reg_snap_delta — co hardware widzi"*

**Plik:** `analyzer/p4/measurement.p4` (akcja `compute_delta` + tabela `histogram_bin_map`)
**Diagnostyka:** wymagała dodania rejestru `reg_snap_delta` do snapshot wartości
`ig_md.delta` PRZED `histogram_bin_map.apply()`.

---

## 6. PHV per-pipe — rejestry różne między pipe'ami

**Napotkane:** Pomiary pokazały rozbieżność między `reg_min` (agregowane
przez `min` ze wszystkich pipe'ów) a `reg_snap_delta` (agregowane przez
`max`). Konkretnie dla scenariusza Plan A z 4 kierunkami DUT:

- `reg_min[0]` (DUT) = 967 ns
- `reg_max[0]` (DUT) = 1029 ns
- `reg_snap_delta[0]` (DUT) = 1640 ns

Wszystkie odczytywane z tego samego rejestru SALU, na tym samym
pakiecie, w tej samej iteracji. Skąd różnica?

**Analiza:** Pakiety DUT lecą przez **dwa różne pipe'y T_P**:

```
Pipe 1: fan-out z portu T_B przez uplink RX_A/B (132, 128) → port serwera
Pipe 2: fan-out z portu T_B przez uplink TX_A/B (288, 292) → port serwera
```

Każdy pipe ma **własną kopię rejestrów SALU**. Pipe 1 widzi delta
~967-1029 ns (krótsza ścieżka), pipe 2 widzi delta ~1640 ns (pełna
trasa T_B → uplink → T_P pipe 2 → port serwera).

Agregator min daje min(pipe 1, pipe 2) = 967 (z pipe 1).
Agregator max daje max(pipe 1, pipe 2) = 1640 (z pipe 2).
**Histogram zlicza wszystkie pakiety**, daje średnią ~1635 ns
(spojrzeniana na pikę bin 81-82).

**Konsekwencja:** Wartości publikowane w artykule (§6) używają
**histogramowej średniej** dla scenariuszy mieszczących się w zakresie
tabeli (<65 μs), oraz **`reg_min`/`reg_max` per-pipe** dla scenariuszy
poza zakresem (l2l3_recirc2 = ~200 μs). Per-pipe diagnostyka jest
dostępna przez rejestr `reg_snap_delta` (agregowany jako max).

**Commits:**
- `89` w `KRiT2026-P4`: *"fix stats.py — sum() per-pipe dla count i sum, max() tylko dla min/max"*
- `103` (task): *"Diagnostyka Bug B — snap_delta register w P4"*

**Plik:** `analyzer/controller/stats.py` (funkcja `_read_register`
z parametrem `aggregator`)

---

## Podsumowanie

Wszystkie 6 ograniczeń zostało napotkane podczas budowy platformy
pomiarowej i obeszto **bez recyrkulacji** w głównym potoku pomiarowym
T_P. Recyrkulacja jest używana wyłącznie:

- dla **strumienia kalibracyjnego** (baseline), opisanego w §3 artykułu —
  port recyrkulacyjny per-pipe (D_P 68, 196, 324, 452)
- w **trzecim badanym programie** P4 (`l2l3_recirc2.p4`), gdzie jest
  **przedmiotem pomiaru** (`MAX_RECIRC=2` w pipe 0 T_B)

Większość obejść to drobne modyfikacje kodu P4 (kilka linii); cztery
wymagały restrukturyzacji lub diagnostyki post-kompilacyjnej (analiza
`context.json` i `phv_allocation_*.log` w katalogu build).

Lista poniżej wymienia narzędzia diagnostyczne pomocne przy podobnych
analizach Tofino TNA + bf-p4c:

- `$SDE/share/tofinopd/<program>/tofino/pipe/context.json` — pełna
  struktura akcji, rejestrów i tabel po kompilacji
- `$SDE/share/tofinopd/<program>/tofino/pipe/logs/phv_allocation_*.log` —
  rozmieszczenie pól w kontenerach PHV
- `$SDE/share/tofinopd/<program>/tofino/pipe/logs/mau.json` — MAU stage
  placement i input crossbar mapping
- `bfrt_python` w bfshell — odczyt tabel i rejestrów z hardware z
  agregacją per-pipe lub `pipe_id=0xffff`

## Wkład w paper KRiT 2026

Artykuł cytuje ten dokument jako źródło szczegółowych ograniczeń
implementacyjnych. Punkty wymienione w §7 paperu odpowiadają sekcjom
1-6 powyżej (w tej samej kolejności). Recenzent zainteresowany techniczną
warstwą Tofino TNA znajdzie tu pełne fragmenty kodu, błędy kompilatora,
sposób ich diagnozy i commit hash dla każdej zmiany.

---

*Dokument: 6 czerwca 2026. Autorzy: zespół KRiT 2026.
Źródło: faktyczne ograniczenia napotkane podczas implementacji
w SDE 9.13.4 (Tofino-1, Wedge100BF-65X jako T_P i Wedge100BF-32X jako T_B).*
