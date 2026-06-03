# Kalibracja baseline: recyrkulacja vs DAC

## Problem

Znacznik czasu `TS1` pobierany z wejściowego MAC obejmuje cały narzut
przejścia pakietu przez wewnętrzny potok przełącznika pomiarowego 65X.
Dla typowego programu z 8–10 stages MAU i 5 SALU update'ami narzut ten
wynosi ~300–400 ns. Aby zmierzyć **rzeczywiste** opóźnienie DUT, musimy
ten narzut odjąć.

## Dwa warianty kalibracji

Implementacja wspiera **dwa warianty** ścieżki baseline, wybierane przez
makro w `p4/measurement.p4`:

```c
#define BASELINE_MODE_RECIRC   // wariant A — default
// #define BASELINE_MODE_DAC   // wariant B
```

### Wariant A: recyrkulacja (default)

Pakiet baseline jest kierowany na **port recyrkulacyjny** ASIC (D_P 68 dla
pipe 0). Tofino-1 automatycznie zwraca pakiet do ingressu tego samego
pipe'a, bez fizycznego wyjścia poza chip.

**Co obejmuje Δ_baseline_recirc:**

```
parser ingress → MAU stages → TM → egress MAU → deparser →
egress MAC (wirtualny port recirc) → wewnętrzny FIFO recirc →
parser ingress (po recyrkulacji)
```

**Plusy:**

- Działa **bez fizycznego sprzętu** — można rozwijać i testować kod nawet
  bez podłączonych kabli DAC.
- Nie zużywa portu front-panel — wszystkie 65 portów dostępne na normalny ruch.
- Niezawodne — żaden mechanizm fizyczny (kabel, SerDes, link autoneg) nie
  może zawieść.

**Minusy:**

- Pomija fizyczny SerDes egress MAC oraz fizyczny MAC ingress — wewnętrzny
  FIFO recyrkulacji jest nieco szybszy niż egress MAC + kabel + ingress MAC.
- Różnica względem prawdziwego ruchu DUT wynosi rzędu kilkudziesięciu ns —
  do empirycznego oszacowania po podłączeniu DAC.

### Wariant B: fizyczna pętla DAC

Pakiet baseline jest kierowany na port fizyczny (D_P 308), wychodzi przez
SerDes + egress MAC, kabel DAC zwraca go do innego portu fizycznego
(D_P 148), gdzie wchodzi przez ingress MAC.

**Co obejmuje Δ_baseline_DAC:**

```
parser ingress → MAU stages → TM → egress MAU → deparser →
egress MAC (port 308) → SerDes → kabel DAC →
SerDes → ingress MAC (port 148) → parser ingress
```

**Plusy:**

- Pokrywa **dokładnie te same** stages co ścieżka DUT (bez DUT) — różnica
  to tylko fakt, że pakiet nie przechodzi przez DUT i przez 2 kable DAC
  do DUT, ale przez jeden kabel DAC w pętli.

**Minusy:**

- Wymaga fizycznego podłączenia kabla DAC obydwoma końcami w 65X.
- Zużywa 2 porty front-panel (które mogłyby służyć do innego ruchu).
- Mechanizm autoneg linku może zawieść (jak doświadczyliśmy w
  pierwotnej konfiguracji — kabel nie podniósł linku).

## Plan walidacji

Po powrocie do laboratorium (po świętach 2026-06-07+):

1. Uruchomić pomiar w **wariancie A** (recyrkulacja).
2. Zapisać Δ_baseline_recirc dla różnych obciążeń (10%, 50%, 90% line-rate).
3. Podłączyć kabel DAC obydwoma końcami w 65X (porty 308 i 148).
4. Uruchomić pomiar w **wariancie B** (DAC). Zapisać Δ_baseline_DAC.
5. Obliczyć:
   - **ε = Δ_baseline_DAC − Δ_baseline_recirc**
   - Spodziewana wartość: **15–40 ns** (różnica MAC + SerDes + kabel vs
     FIFO recirc).
6. Jeśli ε jest stabilne (jitter < 5 ns), w artykule można podać **jedno**
   pomiarowe Δ_DUT_real z notą o niepewności ±ε/2.
7. Jeśli ε jest niestabilne, wybieramy **wariant B** jako bardziej wiarygodny
   (mimo straconych 2 portów).

## Empiryczne dane (do wypełnienia)

| Tryb baseline | Δ_min [ns] | Δ_max [ns] | Δ_avg [ns] | Jitter [ns] | Data pomiaru |
|---|---:|---:|---:|---:|---|
| RECIRC | TBD | TBD | TBD | TBD | TBD |
| DAC    | TBD | TBD | TBD | TBD | TBD |

| ε = DAC − RECIRC [ns] | Średnia | Std dev | N pomiarów |
|---|---:|---:|---:|
| TBD | TBD | TBD | TBD |

## Konkluzja dla artykułu

W bieżącej wersji artykułu opisujemy **oba** warianty. Wyniki pomiarowe
prezentujemy z trybu **A** (recyrkulacja), z notą metodologiczną o
walidacji krzyżowej przez wariant B (planowana po deadline'cie KRiT —
może wejść do rebuttal lub do extended journal version).
