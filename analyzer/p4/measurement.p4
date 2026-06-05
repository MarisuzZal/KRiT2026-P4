// =============================================================================
//  measurement.p4 — Platforma pomiarowa dla Wedge 100BF-65X (Intel Tofino-1)
//
//  Artykuł KRiT 2026: "Tofino jako platforma pomiarowa: nanosekundowa analiza
//  opóźnień ruchu w sieci"  (Rekosz, Zmuda, Grzelski, Jalowski, Żal — zgłoszenie).
//
//  Funkcje:
//    (1) Fan-in:  agregacja 4 portów serwera → 2 uplinki do DUT
//                 + 1 ścieżka kalibracyjna (recirc port lub DAC loop)
//    (2) Fan-out: rozproszenie ruchu wracającego z DUT / baseline
//                 do 4 portów serwera (klucz: dst_addr LPM)
//    (3) Stamping znacznika czasu MAC (TS1 = ingress_mac_tstamp) w pakietach
//        idących do DUT/baseline; odczyt znacznika i obliczenie
//        Δ = t_RX − t_TX dla pakietów wracających
//    (4) Statystyki SALU (min/max/sum/count) — rejestry współdzielone DUT+base
//    (5) Histogram 128 binów — osobne rejestry dla ścieżki DUT i baseline
//    (6) Per-flow sequence number (do detekcji utraty / out-of-order)
//
//  Tryby kalibracji (przełączane przez #define poniżej):
//    BASELINE_MODE_RECIRC  — pętla wewnętrzna przez port recyrkulacyjny ASIC
//    BASELINE_MODE_DAC     — fizyczna pętla DAC obydwoma końcami w 65X
//
//  Korekta: Δ_DUT_real = Δ_DUT_zmierzone − Δ_baseline_zmierzone
//  (obliczana w warstwie sterowania, patrz controller/stats.py)
//
//  Target:  Intel Tofino-1, TNA, SDE 9.13.2
// =============================================================================

#include <core.p4>
#include <tna.p4>

// -----------------------------------------------------------------------------
// Wybór trybu baseline — odkomentuj jeden z dwóch:
// -----------------------------------------------------------------------------
#define BASELINE_MODE_RECIRC
// #define BASELINE_MODE_DAC

// -----------------------------------------------------------------------------
// Numery portów (D_P) — z pliku polaczenia_struktura.md
// -----------------------------------------------------------------------------
#define PORT_SRV_TRex0   9w284   // serwer karta #1 (NUMA 0) B1, prefiks 10.3.0.0/16
#define PORT_SRV_TRex1   9w280   // serwer karta #1 (NUMA 0) B0, prefiks 10.2.0.0/16
#define PORT_SRV_TRex2   9w184   // serwer karta #2 (NUMA 1) A1, prefiks 10.1.0.0/16
#define PORT_SRV_TRex3   9w188   // serwer karta #2 (NUMA 1) A0, prefiks 10.0.0.0/16

#define PORT_UPLINK_A    9w60    // do DUT, para A: 10.3 ↔ 10.1
#define PORT_UPLINK_B    9w132   // do DUT, para B: 10.2 ↔ 10.0

#ifdef BASELINE_MODE_RECIRC
  // Port recyrkulacyjny pipe 0; D_P = (pipe<<7) | 68
  #define PORT_BASE_OUT  9w68
  #define PORT_BASE_IN   9w68    // ten sam port — auto-feedback
#endif

#ifdef BASELINE_MODE_DAC
  // Fizyczna pętla DAC obydwoma końcami w 65X
  #define PORT_BASE_OUT  9w308
  #define PORT_BASE_IN   9w148
#endif

#define HIST_BINS        128
#define MAX_FLOWS        256

typedef bit<7>  bin_idx_t;
typedef bit<48> ts_t;
typedef bit<32> delta_t;   // 32-bit — limit SALU Tofino-1; ~4 s zapasu

// =============================================================================
// Definicje nagłówków
// =============================================================================
header ethernet_t {
    bit<48> dst_addr;
    bit<48> src_addr;
    bit<16> ether_type;
}

// Własny nagłówek znacznika czasu — 6 bajtów (tylko ts)
// flow_id i seq przeniesione do ig_metadata_t / SALU; zostają wewnętrznie
// w analizatorze, nie są transportowane na drucie. Pozwala to uniknąć
// konfliktów PHV allocator w akcji stamp (PHV source + action data
// w tej samej PHV container).
header timestamp_t {
    ts_t    tx_ts;       // znacznik TS1 (ingress_mac_tstamp) z momentu wejścia do 65X
}

header ipv4_t {
    bit<4>   version;
    bit<4>   ihl;
    bit<8>   diffserv;
    bit<16>  total_len;
    bit<16>  identification;
    bit<3>   flags;
    bit<13>  frag_offset;
    bit<8>   ttl;
    bit<8>   protocol;
    bit<16>  hdr_checksum;
    bit<32>  src_addr;
    bit<32>  dst_addr;
}

header l4_ports_t {
    bit<16> src_port;
    bit<16> dst_port;
}

struct headers_t {
    ethernet_t   ethernet;
    timestamp_t  ts;       // valid: kierunek S→DUT/Base oraz powrót
    ipv4_t       ipv4;
    l4_ports_t   l4;
}

struct ig_metadata_t {
    delta_t     delta;            // wyliczone Δ (tylko dla pakietów wracających)
    bit<16>     delta_lo;         // dolne 16 bitów Δ — klucz range-match histogramu
    bit<1>      is_returning;     // 1 = pakiet wraca (z DUT lub baseline)
    bit<1>      path_is_baseline; // 1 = ścieżka baseline, 0 = DUT (indeks rejestru)
    bin_idx_t   bin;              // indeks binu histogramu (0..127)
    bit<16>     flow_id;          // wypełnione z akcji tabeli
    bit<32>     seq_value;        // wypełnione przez SALU
    bit<1>      drop_flag;
}

// =============================================================================
// Parser ingress
// =============================================================================
parser SwitchIngressParser(
    packet_in pkt,
    out headers_t hdr,
    out ig_metadata_t ig_md,
    out ingress_intrinsic_metadata_t ig_intr_md
) {
    state start {
        pkt.extract(ig_intr_md);
        pkt.advance(PORT_METADATA_SIZE);
        transition parse_ethernet;
    }
    state parse_ethernet {
        pkt.extract(hdr.ethernet);
        transition select(hdr.ethernet.ether_type) {
            16w0xABCD: parse_timestamp;   // pakiet niesie nasz znacznik (wraca)
            16w0x0800: parse_ipv4;
            default:   accept;
        }
    }
    state parse_timestamp {
        pkt.extract(hdr.ts);
        transition parse_ipv4;
    }
    state parse_ipv4 {
        pkt.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            8w6:     parse_l4;
            8w17:    parse_l4;
            default: accept;
        }
    }
    state parse_l4 {
        pkt.extract(hdr.l4);
        transition accept;
    }
}

// =============================================================================
// Ingress: routing + stamping + pomiar
// =============================================================================
control SwitchIngress(
    inout headers_t hdr,
    inout ig_metadata_t ig_md,
    in ingress_intrinsic_metadata_t ig_intr_md,
    in ingress_intrinsic_metadata_from_parser_t ig_prsr_md,
    inout ingress_intrinsic_metadata_for_deparser_t ig_dprsr_md,
    inout ingress_intrinsic_metadata_for_tm_t ig_tm_md
) {
    // -------------------------------------------------------------------------
    // Akcje stampingu (kierunek S→DUT lub S→Base)
    // -------------------------------------------------------------------------
    action stamp_to_dut(PortId_t egress_port, bit<16> flow_id) {
        hdr.ts.setValid();
        hdr.ts.tx_ts = ig_intr_md.ingress_mac_tstamp;
        hdr.ethernet.ether_type = 16w0xABCD;
        ig_tm_md.ucast_egress_port = egress_port;
        ig_md.flow_id = flow_id;
    }
    action stamp_to_baseline(PortId_t egress_port, bit<16> flow_id) {
        hdr.ts.setValid();
        hdr.ts.tx_ts = ig_intr_md.ingress_mac_tstamp;
        hdr.ethernet.ether_type = 16w0xABCD;
        ig_tm_md.ucast_egress_port = egress_port;
        ig_md.flow_id = flow_id;
    }

    // -------------------------------------------------------------------------
    // Akcje odczytu (kierunek DUT→S lub Base→S)
    //   Oznaczają ścieżkę (DUT/baseline); Δ obliczana w głównym apply
    // -------------------------------------------------------------------------
    action read_from_dut(PortId_t egress_port) {
        ig_md.is_returning = 1;
        ig_md.path_is_baseline = 0;
        ig_tm_md.ucast_egress_port = egress_port;
    }
    action read_from_baseline(PortId_t egress_port) {
        ig_md.is_returning = 1;
        ig_md.path_is_baseline = 1;
        ig_tm_md.ucast_egress_port = egress_port;
    }

    action drop() {
        ig_dprsr_md.drop_ctl = 1;
        ig_md.drop_flag = 1;
    }

    // -------------------------------------------------------------------------
    // Tabela routingu — klucz (ingress_port, dst_addr LPM)
    //   ~20 wpisów dla DUT + 4-8 wpisów dla baseline
    // -------------------------------------------------------------------------
    table port_routing {
        key = {
            ig_intr_md.ingress_port : exact;
            hdr.ipv4.dst_addr        : lpm;
        }
        actions = {
            stamp_to_dut;
            stamp_to_baseline;
            read_from_dut;
            read_from_baseline;
            drop;
        }
        default_action = drop();
        size = 64;
    }

    // -------------------------------------------------------------------------
    // SALU: licznik sekwencji per strumień (256 strumieni × 32-bit)
    // -------------------------------------------------------------------------
    Register<bit<32>, bit<8>>(MAX_FLOWS, 0) reg_seq_per_flow;
    RegisterAction<bit<32>, bit<8>, bit<32>>(reg_seq_per_flow) get_next_seq = {
        void apply(inout bit<32> value, out bit<32> rv) {
            value = value + 1;
            rv = value;
        }
    };

    // -------------------------------------------------------------------------
    // Obliczenie Δ — pojedyncze odejmowanie 48-bit
    // -------------------------------------------------------------------------
    action compute_delta() {
        // 32-bit subtract — wystarcza dla pomiaru (range 4.3 s).
        // delta_lo bierzemy ze SLICE'A już-obliczonego delta (32->16-bit slice
        // jest tani w jednym PHV container), nie z osobnego slice z 48-bit
        // diff (który bf-p4c może nieoczekiwanie zoptymalizować do zera).
        bit<32> hi = (bit<32>)ig_intr_md.ingress_mac_tstamp;
        bit<32> lo = (bit<32>)hdr.ts.tx_ts;
        ig_md.delta    = hi - lo;
        ig_md.delta_lo = ig_md.delta[15:0];
    }

    // -------------------------------------------------------------------------
    // Tabela range-match: Δ → indeks binu histogramu
    //   Programowana z kontrolera (skala zależna od wstępnych pomiarów min/max)
    // -------------------------------------------------------------------------
    action set_bin(bin_idx_t b) { ig_md.bin = b; }

    table histogram_bin_map {
        key = { ig_md.delta_lo : range; }   // 16-bit — TNA range-match budget
        actions = { set_bin; NoAction; }
        default_action = NoAction;
        size = HIST_BINS;
    }

    // -------------------------------------------------------------------------
    // Statystyki min/max/sum/count — REJESTRY WSPÓŁDZIELONE
    //   index 0 = DUT, index 1 = baseline (path_is_baseline)
    //   Oszczędza 4 stages MAU względem dwóch osobnych kompletów
    // -------------------------------------------------------------------------
    Register<delta_t, bit<1>>(2, 32w0xFFFFFFFF) reg_min;
    RegisterAction<delta_t, bit<1>, delta_t>(reg_min) update_min = {
        void apply(inout delta_t value, out delta_t rv) {
            if (ig_md.delta < value) { value = ig_md.delta; }
            rv = value;
        }
    };

    Register<delta_t, bit<1>>(2, 32w0) reg_max;
    RegisterAction<delta_t, bit<1>, delta_t>(reg_max) update_max = {
        void apply(inout delta_t value, out delta_t rv) {
            if (ig_md.delta > value) { value = ig_md.delta; }
            rv = value;
        }
    };

    Register<bit<32>, bit<1>>(2, 0) reg_sum_lo;
    RegisterAction<bit<32>, bit<1>, bit<32>>(reg_sum_lo) update_sum_lo = {
        void apply(inout bit<32> value, out bit<32> rv) {
            value = value + ig_md.delta;
            rv = value;
        }
    };

    Register<bit<32>, bit<1>>(2, 0) reg_count;
    RegisterAction<bit<32>, bit<1>, bit<32>>(reg_count) update_count = {
        void apply(inout bit<32> value, out bit<32> rv) {
            value = value + 1;
            rv = value;
        }
    };

    // -------------------------------------------------------------------------
    // Histogramy — dwa osobne rejestry (gateway wybiera DUT vs baseline)
    //   Tofino nie pozwala na "computed bit-slice index", więc rozdzielamy
    // -------------------------------------------------------------------------
    Register<bit<32>, bin_idx_t>(HIST_BINS, 0) reg_hist_dut;
    RegisterAction<bit<32>, bin_idx_t, bit<32>>(reg_hist_dut) bump_hist_dut = {
        void apply(inout bit<32> value, out bit<32> rv) {
            value = value + 1;
            rv = value;
        }
    };

    Register<bit<32>, bin_idx_t>(HIST_BINS, 0) reg_hist_base;
    RegisterAction<bit<32>, bin_idx_t, bit<32>>(reg_hist_base) bump_hist_base = {
        void apply(inout bit<32> value, out bit<32> rv) {
            value = value + 1;
            rv = value;
        }
    };

    // =========================================================================
    // Główna logika
    // =========================================================================
    apply {
        // 1) Routing — ustaw egress_port + oznacz kierunek
        port_routing.apply();

        // 2) Stamping numeru sekwencji per strumień (tylko TX)
        if (hdr.ts.isValid() && ig_md.is_returning == 0) {
            ig_md.seq_value = get_next_seq.execute(ig_md.flow_id[7:0]);
        }

        // 3) Pomiar (tylko dla pakietów wracających)
        if (ig_md.is_returning == 1 && hdr.ts.isValid()) {
            compute_delta();
            histogram_bin_map.apply();
            update_min.execute(ig_md.path_is_baseline);
            update_max.execute(ig_md.path_is_baseline);
            update_sum_lo.execute(ig_md.path_is_baseline);
            update_count.execute(ig_md.path_is_baseline);
            if (ig_md.path_is_baseline == 0) {
                bump_hist_dut.execute(ig_md.bin);
            } else {
                bump_hist_base.execute(ig_md.bin);
            }
            // Zdjąć nasz nagłówek przed wysłaniem do serwera
            hdr.ts.setInvalid();
            hdr.ethernet.ether_type = 16w0x0800;
        }
    }
}

// =============================================================================
// Deparser ingress
// =============================================================================
control SwitchIngressDeparser(
    packet_out pkt,
    inout headers_t hdr,
    in ig_metadata_t ig_md,
    in ingress_intrinsic_metadata_for_deparser_t ig_dprsr_md
) {
    apply {
        pkt.emit(hdr.ethernet);
        pkt.emit(hdr.ts);
        pkt.emit(hdr.ipv4);
        pkt.emit(hdr.l4);
    }
}

// =============================================================================
// Egress — pusty (cała logika w ingress)
// =============================================================================
struct eg_metadata_t {}

parser SwitchEgressParser(
    packet_in pkt,
    out headers_t hdr,
    out eg_metadata_t eg_md,
    out egress_intrinsic_metadata_t eg_intr_md
) {
    state start { pkt.extract(eg_intr_md); transition accept; }
}

control SwitchEgress(
    inout headers_t hdr,
    inout eg_metadata_t eg_md,
    in egress_intrinsic_metadata_t eg_intr_md,
    in egress_intrinsic_metadata_from_parser_t eg_prsr_md,
    inout egress_intrinsic_metadata_for_deparser_t eg_dprsr_md,
    inout egress_intrinsic_metadata_for_output_port_t eg_oport_md
) { apply {} }

control SwitchEgressDeparser(
    packet_out pkt,
    inout headers_t hdr,
    in eg_metadata_t eg_md,
    in egress_intrinsic_metadata_for_deparser_t eg_dprsr_md
) { apply {} }

// =============================================================================
// Pipeline
// =============================================================================
Pipeline(
    SwitchIngressParser(),
    SwitchIngress(),
    SwitchIngressDeparser(),
    SwitchEgressParser(),
    SwitchEgress(),
    SwitchEgressDeparser()
) pipe;

Switch(pipe) main;
