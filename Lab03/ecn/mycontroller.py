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

#根据topology.json及拓扑图可以得出各设备相连接的端口
S1_TO_H1_PORT = 2
S1_TO_H11_PORT = 1
S1_TO_S2_PORT = 3
S1_TO_S3_PORT = 4
S2_TO_H2_PORT = 2
S2_TO_H22_PORT = 1
S2_TO_S1_PORT = 3
S2_TO_S3_PORT = 4
S3_TO_H3_PORT = 1
S3_TO_S1_PORT = 2
S3_TO_S2_PORT = 3

#增加一个match_len函数，以根据不同情况来修改掩码的大小
#根据原来的sx-runtime.json来编写函数，以实现流表的动态下发
def writeTranRules(p4info_helper, ingress_sw,
                      dst_ip_addr, dst_next_addr, tran_port, match_len):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": (dst_ip_addr, match_len)
        },
        action_name="MyIngress.ipv4_forward",
        action_params={
            "dstAddr":dst_next_addr,
            "port":tran_port
        })
    ingress_sw.WriteTableEntry(table_entry)
    print("Installed switch forwarding rule on %s" % ingress_sw.name)

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

        #根据sx-runtime.json来填入参数的实际值
        writeTranRules(p4info_helper, ingress_sw=s1, dst_ip_addr="10.0.1.1",
                         dst_next_addr="08:00:00:00:01:01",tran_port=S1_TO_H1_PORT,match_len=32)
        writeTranRules(p4info_helper, ingress_sw=s1, dst_ip_addr="10.0.1.11",
                         dst_next_addr="08:00:00:00:01:11",tran_port=S1_TO_H11_PORT,match_len=32)
        writeTranRules(p4info_helper, ingress_sw=s1, dst_ip_addr="10.0.2.0",
                         dst_next_addr="08:00:00:00:02:00",tran_port=S1_TO_S2_PORT,match_len=24)
        writeTranRules(p4info_helper, ingress_sw=s1, dst_ip_addr="10.0.3.0",
                         dst_next_addr="08:00:00:00:03:00",tran_port=S1_TO_S3_PORT,match_len=24)

        writeTranRules(p4info_helper, ingress_sw=s2, dst_ip_addr="10.0.2.2",
                         dst_next_addr="08:00:00:00:02:02",tran_port=S2_TO_H2_PORT,match_len=32)
        writeTranRules(p4info_helper, ingress_sw=s2, dst_ip_addr="10.0.2.22",
                         dst_next_addr="08:00:00:00:02:22",tran_port=S2_TO_H22_PORT,match_len=32)
        writeTranRules(p4info_helper, ingress_sw=s2, dst_ip_addr="10.0.1.0",
                         dst_next_addr="08:00:00:00:01:00",tran_port=S2_TO_S1_PORT,match_len=24)
        writeTranRules(p4info_helper, ingress_sw=s2, dst_ip_addr="10.0.3.0",
                         dst_next_addr="08:00:00:00:03:00",tran_port=S2_TO_S3_PORT,match_len=24)

        writeTranRules(p4info_helper, ingress_sw=s3, dst_ip_addr="10.0.3.3",
                         dst_next_addr="08:00:00:00:03:03",tran_port=S3_TO_H3_PORT,match_len=32)
        writeTranRules(p4info_helper, ingress_sw=s3, dst_ip_addr="10.0.1.0",
                         dst_next_addr="08:00:00:00:01:00",tran_port=S3_TO_S1_PORT,match_len=24)
        writeTranRules(p4info_helper, ingress_sw=s3, dst_ip_addr="10.0.2.0",
                         dst_next_addr="08:00:00:00:02:00",tran_port=S3_TO_S2_PORT,match_len=24)

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
    #配置要对应修改
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/ecn.p4.p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/ecn.json')
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
