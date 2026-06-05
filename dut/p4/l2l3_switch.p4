// =============================================================================
//  l2l3_switch.p4 — klasyczny przełącznik L2/L3 dla Tofino #2 (DUT)
//
//  Logika:
//    (1) Parser: Ethernet + IPv4 (opcjonalnie).
//    (2) Ingress:
//          a. Tablica mac_lookup (exact match na dst MAC) — jeśli trafiona,
//             ustawia egress_port (warstwa 2).
//          b. Tablica ipv4_lookup (LPM na dst IP) — jeśli trafiona,
//             ustawia egress_port (warstwa 3, dekrementacja TTL).
//          Priorytet: L2 hit > L3 hit > drop.
//
//  Reprezentuje typową konfigurację przełącznika w centrum danych.
//
//  Target: Intel Tofino-1 (Wedge 100BF-32X), TNA, SDE 9.13.2
// =============================================================================

#include <core.p4>
#include <tna.p4>

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

// Bridge timestamp header (6 bajtów) — wstawiany przez T1 measurement.p4
// dla pakietów DUT. T2 musi go ekstrahowć i zachować, inaczej parser
// idzie do `default: accept` i pakiet dropuje się w ipv4_lookup
// (hdr.ipv4 invalid).
header timestamp_t {
    bit<48> tx_ts;
}

struct headers_t {
    ethernet_t  ethernet;
    timestamp_t ts;        // valid gdy pakiet niesie znacznik T1
    ipv4_t      ipv4;
}

struct ig_metadata_t {
    bit<1> l2_hit;
    bit<1> l3_hit;
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
        transition parse_ethernet;
    }
    state parse_ethernet {
        pkt.extract(hdr.ethernet);
        transition select(hdr.ethernet.ether_type) {
            16w0xABCD: parse_timestamp;   // pakiet niesie znacznik T1
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
    action set_egress_l2(PortId_t port) {
        ig_tm_md.ucast_egress_port = port;
        ig_md.l2_hit = 1;
    }

    action set_egress_l3(PortId_t port, bit<48> new_dst_mac) {
        ig_tm_md.ucast_egress_port = port;
        hdr.ethernet.dst_addr = new_dst_mac;          // przepisanie next-hop MAC
        hdr.ethernet.src_addr = 48w0x000000000001;    // MAC routera (przykład)
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
        ig_md.l3_hit = 1;
    }

    action drop() {
        ig_dprsr_md.drop_ctl = 1;
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
        mac_lookup.apply();
        if (ig_md.l2_hit == 0 && hdr.ipv4.isValid()) {
            ipv4_lookup.apply();
        } else if (ig_md.l2_hit == 0) {
            drop();
        }
    }
}

control SwitchIngressDeparser(
    packet_out pkt, inout headers_t hdr, in ig_metadata_t ig_md,
    in ingress_intrinsic_metadata_for_deparser_t ig_dprsr_md
) {
    apply {
        pkt.emit(hdr.ethernet);
        pkt.emit(hdr.ts);          // tylko jeśli valid (idzie z T1)
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
