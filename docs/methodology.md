# Metodyka pomiaru opóźnień

## Cel

Zmierzyć opóźnienie wprowadzane przez badane urządzenie (DUT) — przełącznik
**Edgecore Wedge 100BF-32X** — z **rozdzielczością nanosekundową** i
**bez sprzętu referencyjnego klasy testera** (Spirent, Keysight).

## Zasada działania

Drugi egzemplarz tego samego rodzaju przełącznika (**Edgecore Wedge 100BF-65X**)
pełni rolę **inteligentnego TAP-a pomiarowego**:

1. Pakiet wchodzi z serwera na port S\* (jeden z 4 dostępnych D_P 284/280/184/188).
2. W ingressie 65X pakiet otrzymuje **znacznik czasu** `TS1` z wejściowego MAC,
   który jest zapisywany w 16-bajtowym nagłówku wstawianym za Ethernetem.
3. Pakiet idzie do DUT (Uplink_A: D_P 60, lub Uplink_B: D_P 132).
4. DUT realizuje swoją logikę (program P4 podlegający ocenie).
5. Pakiet wraca do 65X przez drugi uplink.
6. 65X odczytuje znacznik z nagłówka, oblicza
   **Δ = TS1\_powrót − TS1\_zapisany\_w\_pakiecie**,
   aktualizuje rejestry SALU (min/max/sum/count) i histogram (128 binów),
   zdejmuje nagłówek i forwarduje pakiet do serwera.

## Co dokładnie mierzy Δ

```
Δ = [pipeline 65X TX]   ← stały narzut, wynika z konstrukcji tego mechanizmu
  + [kabel TX do DUT]
  + [DUT (cała logika)]
  + [kabel RX z DUT]
  + (RX-side TS1 jest stempowane PRZED pipeline'em RX, więc nie wchodzi)
```

Składnik `[pipeline 65X TX]` to ~300–400 ns (zależnie od liczby stages i
zajętości SRAM) i jest **stałą** dla danej konfiguracji programu P4.

## Eliminacja narzutu — automatyczna kalibracja online

Aby usunąć stały narzut pipeline'u 65X z wyniku, równolegle do strumienia
testowego generowany jest **strumień kalibracyjny** kierowany przez krótką
ścieżkę zamkniętą wewnątrz 65X (bez DUT). Dla obu strumieni prowadzone są
**osobne** komplety rejestrów statystycznych. Wynik kalibrowany:

```
Δ_DUT_rzeczywiste = Δ_DUT_zmierzone − Δ_baseline_zmierzone
```

Strumień kalibracyjny przechodzi przez **ten sam** ASIC w **tych samych
warunkach** (temperatura, obciążenie pipeline'u, kolejka TM), więc jego
wartość odzwierciedla aktualny stan narzutu — bez konieczności osobnej sesji
kalibracyjnej.

Szczegóły wyboru ścieżki kalibracyjnej: [`calibration.md`](calibration.md).

## Co tracimy / na co uważać

1. **Δ obejmuje też kable**. Kable DAC QSFP28 100 G mają opóźnienie
   propagacji ~5 ns/m. Jeśli kable do DUT i kable w pętli baseline mają
   różne długości, do końcowego wyniku wchodzi różnica
   (zaprojektować jednakowe długości lub odjąć skalibrowane wartości).

2. **Δ jest mierzone w 65X** — nie w DUT. Nie znamy momentu wejścia/wyjścia
   pakietu z DUT z dokładnością lepszą niż propagacja kabla. To jednak
   wystarczająca dokładność dla typowych opóźnień DUT (setki ns – µs).

3. **Mechanizm zakłada że pakiet wraca** (przepływ hairpin). DUT musi być
   skonfigurowany tak, by pakiet z Uplink_A wracał przez Uplink_B (lub na
   odwrót).

4. **Rozdzielczość** ograniczona przez zegar Tofino-1 (1,22 GHz, tick = 0,819 ns).
   Dla wartości Δ mniejszych niż ~30 ticków (~25 ns) rozdzielczość jest
   praktycznie ograniczona przez jitter pipeline'u 65X (rzędu 10–20 ns).

## Skalowanie

Mechanizm jest niezależny od liczby strumieni testowych — wszystkie pakiety
kierowane na ścieżkę DUT trafiają do tych samych rejestrów statystycznych.
Można:

- Rozdzielić statystyki **per flow_id** (256 strumieni × osobne min/max/avg)
  — kosztem 4× więcej SALU stages, lub
- Wykorzystać **jeden zestaw rejestrów** dla wszystkich strumieni
  (obecna implementacja) — bardziej oszczędne, ale traci się rozdzielenie.

## Powiązanie z artykułem

Sekcja "Mechanizm pomiaru opóźnień" papera KRiT 2026 opisuje powyższą
metodykę. Tabele wyników w sekcji "Wyniki" pochodzą z plików CSV
generowanych przez `analyzer/analyzer/controller/main.py`.

Pełne źródła: <https://github.com/MarisuzZal/KRiT2026-P4>
