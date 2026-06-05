// =============================================================================
//  l2l3_recirc2.p4 — przełącznik L2/L3 z dwukrotną recyrkulacją
//
//  Cel: zmierzyć wpływ recyrkulacji na opóźnienie pakietu.
//  Logika:
//    Faza 0 (pierwsze wejście pakietu): zapis licznika recirc_count=1 w
//           nagłówku bridge, skierowanie pakietu na port recyrkulacyjny.
//    Faza 1 (po pierwszej recyrkulacji): odczyt licznika, recirc_count=2,
//           ponownie skierowanie na port recyrkulacyjny.
//    Faza 2 (po drugiej recyrkulacji): pełna logika L2/L3, wysłanie pakietu
//           do portu wyjściowego z usunięciem nagłówka bridge.
//
//  Port recyrkulacyjny zgodnie z TNA App Note §5.1 — auto-feedback na ten
//  sam pipe. Typowo D_P = (pipe << 7) | 68. Dostosować do konfiguracji
//  Tofino #2 (Wedge 100BF-32X) po sprawdzeniu `pm show`.
//
//  Target: Intel Tofino-1, TNA, SDE 9.13.2
// =============================================================================

#include <core.p4>
#include <tna.p4>

#define RECIRC_PORT 9w68          // port recyrkulacyjny pipe 0; dostosować
#define MAX_RECIRC  2             // liczba wymaganych recyrkulacji

// -----------------------------------------------------------------------------
// Nagłówki
// -----------------------------------------------------------------------------
header ethernet_t {
    bit<48> dst_addr;
    bit<48> src_addr;
    bit<16> ether_type;
}

header ipv4_t {
    bit<4>  version;
    bit<4>  ihl;
    bit<8>  diffserv;
    bit<16> total_len;
    bit<16> identification;
    bit<3>  flags;
    bit<13> frag_offset;
    bit<8>  ttl;
    bit<8>  protocol;
    bit<16> hdr_checksum;
    bit<32> src_addr;
    bit<32> dst_addr;
}

// Nagłówek bridge — licznik recyrkulacji + flagi
header bridge_t {
    bit<3>  recirc_count;
    bit<5>  _pad;
}

struct headers_t {
    bridge_t   bridge;          // valid podczas recyrkulacji
    ethernet_t ethernet;
    ipv4_t     ipv4;
}

struct ig_metadata_t {
    bit<3> recirc_count;
    bit<1> l2_hit;
}
struct eg_metadata_t {}

// -----------------------------------------------------------------------------
// Parser
// -----------------------------------------------------------------------------
parser SwitchIngressParser(
    packet_in pkt,
    out headers_t hdr,
    out ig_metadata_t ig_md,
    out ingress_intrinsic_metadata_t ig_intr_md
) {
    state start {
        pkt.extract(ig_intr_md);
        pkt.advance(PORT_METADATA_SIZE);
        transition select(ig_intr_md.ingress_port) {
            RECIRC_PORT: parse_bridge;     // pakiet wraca z recyrkulacji
            default:     parse_ethernet;   // pakiet pierwszy raz
        }
    }
    state parse_bridge {
        pkt.extract(hdr.bridge);
        transition parse_ethernet;
    }
    state parse_ethernet {
        pkt.extract(hdr.ethernet);
        transition select(hdr.ethernet.ether_type) {
            16w0x0800: parse_ipv4;
            default:   accept;
        }
    }
    state parse_ipv4 {
        pkt.extract(hdr.ipv4);
        transition accept;
    }
}

// -----------------------------------------------------------------------------
// Ingress
// -----------------------------------------------------------------------------
control SwitchIngress(
    inout headers_t hdr,
    inout ig_metadata_t ig_md,
    in ingress_intrinsic_metadata_t ig_intr_md,
    in ingress_intrinsic_metadata_from_parser_t ig_prsr_md,
    inout ingress_intrinsic_metadata_for_deparser_t ig_dprsr_md,
    inout ingress_intrinsic_metadata_for_tm_t ig_tm_md
) {
    // ---- akcje L2/L3 (jak w l2l3_switch.p4) ----
    action set_egress_l2(PortId_t port) {
        ig_tm_md.ucast_egress_port = port;
        ig_md.l2_hit = 1;
    }
    action set_egress_l3(PortId_t port, bit<48> new_dst_mac) {
        ig_tm_md.ucast_egress_port = port;
        hdr.ethernet.dst_addr = new_dst_mac;
        hdr.ethernet.src_addr = 48w0x000000000001;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }
    action drop() { ig_dprsr_md.drop_ctl = 1; }
    action recirc_inc() {
        // Zwiększ licznik i zawróć przez port recyrkulacyjny
        hdr.bridge.setValid();
        hdr.bridge.recirc_count = ig_md.recirc_count + 1;
        hdr.bridge._pad = 0;
        ig_tm_md.ucast_egress_port = RECIRC_PORT;
    }

    table mac_lookup {
        key     = { hdr.ethernet.dst_addr : exact; }
        actions = { set_egress_l2; @defaultonly NoAction; }
        default_action = NoAction;
        size = 1024;
    }
    table ipv4_lookup {
        key     = { hdr.ipv4.dst_addr : lpm; }
        actions = { set_egress_l3; drop; }
        default_action = drop();
        size = 16384;
    }

    apply {
        // Stan recyrkulacji: 0 jeśli pakiet pierwszy raz, n+1 po n-tej recyrkulacji
        // UWAGA: bf-p4c nie pozwala na ternary z isValid() jako warunkiem
        // ("Conditions must be simple comparisons of action_data"). Rozbijamy
        // na init + if.
        ig_md.recirc_count = 0;
        if (hdr.bridge.isValid()) {
            ig_md.recirc_count = hdr.bridge.recirc_count;
        }

        if (ig_md.recirc_count < MAX_RECIRC) {
            // Faza 0 lub 1: recyrkulacja
            recirc_inc();
        } else {
            // Faza 2: właściwa logika L2/L3 i wysłanie
            hdr.bridge.setInvalid();
            mac_lookup.apply();
            if (ig_md.l2_hit == 0 && hdr.ipv4.isValid()) {
                ipv4_lookup.apply();
            } else if (ig_md.l2_hit == 0) {
                drop();
            }
        }
    }
}

control SwitchIngressDeparser(
    packet_out pkt, inout headers_t hdr, in ig_metadata_t ig_md,
    in ingress_intrinsic_metadata_for_deparser_t ig_dprsr_md
) {
    apply {
        pkt.emit(hdr.bridge);     // emitowane tylko jeśli valid (recirc)
        pkt.emit(hdr.ethernet);
        pkt.emit(hdr.ipv4);
    }
}

// -----------------------------------------------------------------------------
// Egress: pusty
// -----------------------------------------------------------------------------
parser SwitchEgressParser(
    packet_in pkt, out headers_t hdr, out eg_metadata_t eg_md,
    out egress_intrinsic_metadata_t eg_intr_md
) { state start { pkt.extract(eg_intr_md); transition accept; } }

control SwitchEgress(
    inout headers_t hdr, inout eg_metadata_t eg_md,
    in egress_intrinsic_metadata_t eg_intr_md,
    in egress_intrinsic_metadata_from_parser_t eg_prsr_md,
    inout egress_intrinsic_metadata_for_deparser_t eg_dprsr_md,
    inout egress_intrinsic_metadata_for_output_port_t eg_oport_md
) { apply {} }

control SwitchEgressDeparser(
    packet_out pkt, inout headers_t hdr, in eg_metadata_t eg_md,
    in egress_intrinsic_metadata_for_deparser_t eg_dprsr_md
) { apply {} }

Pipeline(
    SwitchIngressParser(),
    SwitchIngress(),
    SwitchIngressDeparser(),
    SwitchEgressParser(),
    SwitchEgress(),
    SwitchEgressDeparser()
) pipe;

Switch(pipe) main;
