/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

const bit<16> ETHERTYPE_IPV4 = 0x0800;
const bit<16> ETHERTYPE_ARP  = 0x0806;
const bit<16> ARP_HTYPE_ETHERNET = 0x0001;
const bit<16> ARP_PTYPE_IPV4     = 0x0800;
const bit<8>  ARP_HLEN_ETHERNET  = 6;
const bit<8>  ARP_PLEN_IPV4      = 4;
/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/

typedef bit<9>  port_id_t;
typedef bit<48> mac_addr_t;
typedef bit<32> ipv4_addr_t;

header ethernet_t {
    mac_addr_t dstAddr;
    mac_addr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ipv4_addr_t srcAddr;
    ipv4_addr_t dstAddr;
}

header arp_t {
    bit<16> htype;
    bit<16> ptype;
    bit<8>  hlen;
    bit<8>  plen;
    bit<16> oper;
}

header arp_ipv4_t {
    mac_addr_t  sha;
    ipv4_addr_t spa;
    mac_addr_t  tha;
    ipv4_addr_t tpa;
}

struct headers {
    ethernet_t   ethernet;
    arp_t        arp;
    arp_ipv4_t   arp_ipv4;
    ipv4_t       ipv4;
}

struct metadata {
    ipv4_addr_t ipv4_dst;
    mac_addr_t  mac_dst;
    mac_addr_t  mac_src;
    port_id_t   egress_port;
}

/*************************************************************************
*********************** P A R S E R  ***********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        packet.extract(hdr.ethernet);
	      transition select(hdr.ethernet.etherType){
		          ETHERTYPE_IPV4:parse_ipv4;
              ETHERTYPE_ARP:parse_arp;
		          default:accept;
	            }
    }

    state parse_ipv4{
	     packet.extract(hdr.ipv4);
       meta.ipv4_dst = hdr.ipv4.dstAddr;
       transition accept;
    }

    state parse_arp{
        packet.extract(hdr.arp);
        transition select(hdr.arp.htype, hdr.arp.ptype,
                          hdr.arp.hlen,  hdr.arp.plen){
                          (ARP_HTYPE_ETHERNET,ARP_PTYPE_IPV4,ARP_HLEN_ETHERNET,ARP_PLEN_IPV4):parse_arp_ipv4;
                          default:accept;
                          }
    }

    state parse_arp_ipv4{
        packet.extract(hdr.arp_ipv4);
        meta.ipv4_dst = hdr.arp_ipv4.tpa;
        transition accept;
    }
}

/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {  }
}


/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    action drop() {
        mark_to_drop(standard_metadata);
    }
    action set_dst_info(mac_addr_t dstAddr,mac_addr_t srcAddr,port_id_t  port)
    {
      meta.mac_dst      = dstAddr;
      meta.mac_src      = srcAddr;
      meta.egress_port = port;
    }
    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            drop;
            set_dst_info;
        }
        size = 1024;
        default_action = drop();
    }

    action ipv4_forward() {
        standard_metadata.egress_spec = meta.egress_port;
        hdr.ethernet.dstAddr = meta.mac_dst;
        hdr.ethernet.srcAddr = meta.mac_src;
        hdr.ipv4.ttl         = hdr.ipv4.ttl - 1;
      }

    action send_arp_reply() {
        hdr.ethernet.dstAddr = hdr.arp_ipv4.sha;
        hdr.ethernet.srcAddr = hdr.arp_ipv4.tha;

        hdr.arp.oper         = 2;

        hdr.arp_ipv4.tha     = hdr.arp_ipv4.sha;
        hdr.arp_ipv4.tpa     = hdr.arp_ipv4.spa;
        hdr.arp_ipv4.sha     = meta.mac_dst;
        hdr.arp_ipv4.spa     = meta.ipv4_dst;

        standard_metadata.egress_spec = standard_metadata.ingress_port;
    }
    table forward {
      key = {
        hdr.arp.isValid()      : exact;
        hdr.arp.oper           : ternary;
        hdr.arp_ipv4.isValid() : exact;
        hdr.ipv4.isValid()     : exact;
    }
    actions = {
        ipv4_forward;
        send_arp_reply;
        drop;
    }
    const default_action = drop();
    const entries = {
        ( true,1,true,false) :send_arp_reply();
        ( false, _,false,true) :ipv4_forward();
    }
}

  apply {
        ipv4_lpm.apply();
        forward.apply();
      }
}

/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply {  }
}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers  hdr, inout metadata meta) {
     apply {
	update_checksum(
	    hdr.ipv4.isValid(),
            { hdr.ipv4.version,
	            hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

/*************************************************************************
***********************  D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
	     packet.emit(hdr.ethernet);
       packet.emit(hdr.arp);
       packet.emit(hdr.arp_ipv4);
	     packet.emit(hdr.ipv4);
    }
}

/*************************************************************************
***********************  S W I T C H  *******************************
*************************************************************************/

V1Switch(
MyParser(),
MyVerifyChecksum(),
MyIngress(),
MyEgress(),
MyComputeChecksum(),
MyDeparser()
) main;
