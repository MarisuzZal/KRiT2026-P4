# Walidacja w Tofino Model

## Cel

Sprawdzić **poprawność logiczną** kodu P4 bez dostępu do fizycznego sprzętu.
Symulator nie modeluje zegara MAU, więc **nie zwróci sensownych wartości
Δ** — ale zweryfikuje:

- Pakiet z dst=10.X.X.X jest poprawnie kierowany na uplink_A/B
- Pakiet z dst=10.250.X.X jest poprawnie kierowany na port baseline
- Po powrocie statystyki DUT (count) rosną dla strumieni DUT
- Po powrocie statystyki baseline (count) rosną dla strumieni baseline
- Histogram_bin_map dobrze mapuje Δ → bin

## Uruchomienie

```bash
# 1. Skompiluj i uruchom symulator
SDE=/opt/bf-sde-9.13.2 ./run-tofino-model.sh

# 2. W drugim terminalu — uruchom kontroler (programuje tabele, polluje)
python3 ../analyzer/controller/main.py --duration 30

# 3. W trzecim terminalu — wstrzyknij pakiet testowy przez PTF lub scapy
python3 test_inject.py  # do napisania osobno
```

## Co weryfikujemy

Plik `test_inject.py` (TODO) generuje serię pakietów:

- 100 pakietów `dst=10.1.1.1` z portu 284 → spodziewane: trafiają na
  uplink 60, wracają jako uplink 60 ingress (po fake-DUT recirculate),
  trafiają do reg_count[0] (DUT)
- 100 pakietów `dst=10.250.0.1` z portu 284 → spodziewane: trafiają na
  port 68 (recirc), wracają tym samym portem, trafiają do reg_count[1] (baseline)

Po wstrzyknięciu sprawdzamy że:

- `reg_count[0] == 100` (DUT)
- `reg_count[1] == 100` (baseline)
- Histogram DUT ma wpisy w bin'ach
- Histogram baseline ma wpisy w bin'ach
