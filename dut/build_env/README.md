# dut/build_env — środowisko kompilacji P4 dla Tofino #2 (DUT)

Tymczasowa struktura ułatwiająca kompilację bez ręcznego kopiowania plików.

## Struktura

```
build_env/
├── Build_sh        # skrypt cmake → make → make install
├── src/            # skopiowane ../p4/*.p4 (gitignored, generuje się)
│   └── .gitkeep
├── build/          # build artefakty (gitignored)
└── README.md       # ten plik
```

**Single source of truth:** `dut/p4/*.p4`. Edycje robisz tam,
`Build_sh` synchronizuje do `src/` przed kompilacją.

## Dostępne programy DUT

| Program            | Opis                                                          |
|--------------------|---------------------------------------------------------------|
| `null_switch`      | Minimalny forward (ingress_port → egress_port)                |
| `l2l3_switch`      | L2/L3 switching z LPM                                         |
| `l2l3_recirc2`     | L2/L3 + recyrkulacja (dodatkowe pętle dla pomiarów stress)    |

## Użycie

Na hoście DUT (10.133.5.3):

```bash
# 1. Ustaw zmienne SDE (jednorazowo):
export SDE=/home/student/sde/bf-sde-9.13.4
export SDE_INSTALL=$SDE/install

# 2. Kompiluj (przykład — NullSwitch dla Planu A):
cd dut/build_env
./Build_sh null_switch

# 3. Uruchom switchd:
$SDE/run_switchd.sh -p null_switch

# 4. Załaduj wpisy forward przez kontroler (w drugim terminalu):
SDE_INSTALL=$SDE_INSTALL python3 ../controller/null_switch.py
```

## Common headers (Barefoot proprietary)

Jeśli kiedyś będziemy potrzebować `common/headers.p4` lub `common/util.p4`
(np. parser TofinoIngressParser z Barefoot examples), skopiuj je z:

```
$SDE/pkgsrc/p4-examples/p4_16_programs/common/
```

do `src/common/`. **Nie commituj ich** — mają nagłówek "Barefoot Confidential".
