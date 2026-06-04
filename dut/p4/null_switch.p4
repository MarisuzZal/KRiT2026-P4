// =============================================================================
//  null_switch.p4 — minimalny program P4 dla Tofino #2 (DUT)
//
//  Pakiet jest przekazywany na podstawie portu wejściowego:
//      tablica ingress_to_egress mapuje ingress_port -> egress_port.
//  Brak modyfikacji nagłówków, brak SALU, brak żadnej logiki dodatkowej.
//  Ten program służy jako odniesienie pozwalające ocenić sam narzut potoku
//  przetwarzania pakietu w Tofino.
//
//  Target: Intel Tofino-1 (Wedge 100BF-32X), TNA, SDE 9.13.2
// =============================================================================

#include <core.p4>
#include <tna.p4>

// -----------------------------------------------------------------------------
// Nagłówki (minimalny zestaw — same Ethernet wystarczy do trasowania portowego)
// -----------------------------------------------------------------------------
header ethernet_t {
    bit<48> dst_addr;
    bit<48> src_addr;
    bit<16> ether_type;
}

struct headers_t {
    ethernet_t ethernet;
}

struct ig_metadata_t {}
struct eg_metadata_t {}

// -----------------------------------------------------------------------------
// Parser ingress
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
        pkt.extract(hdr.ethernet);
        transition accept;
    }
}

// -----------------------------------------------------------------------------
// Ingress: pojedyncza tablica forward
// -----------------------------------------------------------------------------
control SwitchIngress(
    inout headers_t hdr,
    inout ig_metadata_t ig_md,
    in ingress_intrinsic_metadata_t ig_intr_md,
    in ingress_intrinsic_metadata_from_parser_t ig_prsr_md,
    inout ingress_intrinsic_metadata_for_deparser_t ig_dprsr_md,
    inout ingress_intrinsic_metadata_for_tm_t ig_tm_md
) {
    action set_egress(PortId_t port) {
        ig_tm_md.ucast_egress_port = port;
    }
    action drop() {
        ig_dprsr_md.drop_ctl = 1;
    }

    table forward {
        key   = { ig_intr_md.ingress_port : exact; }
        actions = { set_egress; drop; }
        default_action = drop();
        size = 32;
    }

    apply { forward.apply(); }
}

control SwitchIngressDeparser(
    packet_out pkt, inout headers_t hdr, in ig_metadata_t ig_md,
    in ingress_intrinsic_metadata_for_deparser_t ig_dprsr_md
) { apply { pkt.emit(hdr.ethernet); } }

// -----------------------------------------------------------------------------
// Egress: pusty (passthrough)
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
