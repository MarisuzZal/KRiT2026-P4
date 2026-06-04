# DUT — programy P4 dla Tofino #2 (Wedge 100BF-32X)

Trzy programy o rosnącej złożoności do scharakteryzowania opóźnienia
$t_\text{DUT}$ przez analizator (Tofino #1):

| Program | Logika | Cel pomiarowy |
|---|---|---|
| `null_switch` | pojedyncza tablica `forward` (port → port) | odniesienie — sam potok |
| `l2l3_switch` | `mac_lookup` (exact) + `ipv4_lookup` (LPM) + TTL | typowy DC switch |
| `l2l3_recirc2` | jak wyżej, plus 2× recyrkulacja przez port recirc | koszt recyrkulacji |

## Kompilacja

```bash
SDE=/opt/bf-sde-9.13.2
for prog in null_switch l2l3_switch l2l3_recirc2; do
    $SDE/install/bin/bf-p4c \
        --target tofino --arch tna \
        -o build/$prog \
        p4/$prog.p4
done
```

## Uruchomienie kontrolerów (po `bf_switchd` z odpowiednim programem)

```bash
# NullSwitch
python3 controller/null_switch.py

# L2/L3 Switch
python3 controller/l2l3_switch.py

# L2/L3 + 2× recirculate
python3 controller/l2l3_recirc2.py
```

## Mapowanie portów DUT

`PORT_FROM_ANALYZER_A` i `PORT_FROM_ANALYZER_B` w `controller/common.py`
są placeholderami. Po fizycznym podłączeniu kabli z Tofino #1 (uplink_A
D_P 60, uplink_B D_P 132) do Tofino #2 — sprawdź `bfshell> pm show`
i zaktualizuj wartości.

## Port recyrkulacyjny (dla `l2l3_recirc2`)

`#define RECIRC_PORT 9w68` w `p4/l2l3_recirc2.p4` to port recyrkulacyjny
pipe 0 (D_P = (pipe << 7) | 68). Dla innego pipe lub w razie potrzeby —
dostosuj.
