#!/usr/bin/env python3
import argparse
import grpc
import os
import sys
from time import sleep

# Import P4Runtime lib from parent utils dir
# Probably there's a better way of doing this.
sys.path.append(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '../../utils/'))
import p4runtime_lib.bmv2
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections
import p4runtime_lib.helper

#给表ecmp_group添加表项 
def writeTranRules_eg(p4info_helper, ingress_sw,
                      dst_ip_addr, base, count):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ecmp_group",
        match_fields={
            "hdr.ipv4.dstAddr": (dst_ip_addr, 32)
        },
        action_name="MyIngress.set_ecmp_select",
        action_params={
            "ecmp_base":base,
            "ecmp_count":count
        })
    ingress_sw.WriteTableEntry(table_entry)
    print("Installed ecmp_group on %s" % ingress_sw.name)

#给表ecmp_nhop添加表项 
def writeTranRules_en(p4info_helper, ingress_sw,
                      select,dmac,ipv4,pt):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ecmp_nhop",
        match_fields={
            "meta.ecmp_select": select
        },
        action_name="MyIngress.set_nhop",
        action_params={
            "nhop_dmac":dmac,
            "nhop_ipv4":ipv4,
            "port":pt
        })
    ingress_sw.WriteTableEntry(table_entry)
    print("Installed ecmp_nhop on %s" % ingress_sw.name)

#给表send_frame添加表项 
def writeTranRules_sf(p4info_helper, egress_sw,
                      pt,mac):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyEgress.send_frame",
        match_fields={
            "standard_metadata.egress_port": pt
        },
        action_name="MyEgress.rewrite_mac",
        action_params={
            "smac": mac
        })
    egress_sw.WriteTableEntry(table_entry)
    print("Installed send_frame on %s" % egress_sw.name)

def readTableRules(p4info_helper, sw):
    print('\n----- Reading tables rules for %s -----' % sw.name)
    for response in sw.ReadTableEntries():
        for entity in response.entities:
            entry = entity.table_entry
            table_name=p4info_helper.get_tables_name(entry.table_id);
            print ("%s:" %table_name)
            for i in entry.match:
                match_name=p4info_helper.get_match_field_name(table_name,i.field_id);
                print ("%s" %(match_name))
                print("(match_type:%r)" % (p4info_helper.get_match_field_value(i),))
            action=entry.action.action
            action_name=p4info_helper.get_actions_name(action.action_id);
            print ("-> %s" %action_name)
            for i in action.params:
                params_name=p4info_helper.get_action_param_name(action_name,i.param_id);
                print (" %s" %params_name)
                print ("(param_value:%r)" %i.value)
            print()

def main(p4info_file_path, bmv2_file_path):
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)

    try:
        s1 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s1',
            address='127.0.0.1:50051',
            device_id=0,
            proto_dump_file='logs/s1-p4runtime-requests.txt')
        s2 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s2',
            address='127.0.0.1:50052',
            device_id=1,
            proto_dump_file='logs/s2-p4runtime-requests.txt')
        s3 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s3',
            address='127.0.0.1:50053',
            device_id=2,
            proto_dump_file='logs/s3-p4runtime-requests.txt')

        s1.MasterArbitrationUpdate()
        s2.MasterArbitrationUpdate()
        s3.MasterArbitrationUpdate()

        s1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s1")
        s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s2")
        s3.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s3")

		#根据sx-runtime.json来补充参数信息 
        writeTranRules_eg(p4info_helper, ingress_sw=s1, dst_ip_addr="10.0.0.1", base=0, count=2)
        writeTranRules_en(p4info_helper, ingress_sw=s1, select=0,dmac="00:00:00:00:01:02", ipv4="10.0.2.2",pt=2)
        writeTranRules_en(p4info_helper, ingress_sw=s1, select=1,dmac="00:00:00:00:01:03", ipv4="10.0.3.3",pt=3)
        writeTranRules_sf(p4info_helper, egress_sw=s1, pt=2, mac= "00:00:00:01:03:00")

        writeTranRules_eg(p4info_helper, ingress_sw=s2, dst_ip_addr="10.0.2.2", base=0, count=1)
        writeTranRules_en(p4info_helper, ingress_sw=s2, select=0, dmac="00:00:00:00:02:02", ipv4="10.0.2.2",pt=1)
        writeTranRules_sf(p4info_helper, egress_sw=s2, pt=1, mac="00:00:00:02:01:00")

        writeTranRules_eg(p4info_helper, ingress_sw=s3, dst_ip_addr="10.0.3.3", base=0, count=1)
        writeTranRules_en(p4info_helper, ingress_sw=s3, select=0,dmac="00:00:00:00:03:03", ipv4="10.0.3.3",pt=1)
        writeTranRules_sf(p4info_helper, egress_sw=s3, pt=1, mac= "00:00:00:03:01:00")

        readTableRules(p4info_helper, s1)
        readTableRules(p4info_helper, s2)
        readTableRules(p4info_helper, s3)
    except KeyboardInterrupt:
        print(" Shutting down.")
    except grpc.RpcError as e:
        printGrpcError(e)
    ShutdownAllSwitchConnections()

if __name__ =='__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
	#对应更改文件路径 
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/load_balance.p4.p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/load_balance.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print("\np4info file not found: %s\nHave you run 'make'?" % args.p4info)
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print("\nBMv2 JSON file not found: %s\nHave you run 'make'?" % args.bmv2_json)
        parser.exit(1)
    main(args.p4info, args.bmv2_json)
