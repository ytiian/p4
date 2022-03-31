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

#根据拓扑图可以得出的交换机到下一跳交换机的出端口
SWITCH_TO_HOST_PORT = 1
S1_TO_S2_PORT = 2
S2_TO_S1_PORT = 2
S1_TO_S3_PORT = 3
S3_TO_S1_PORT = 2
S3_TO_S2_PORT = 3
S2_TO_S3_PORT = 3

#writeTunnelRules函数增加了一个新参数port，因为交换机到下一跳交换机将不一定是2，也可能是3
def writeTunnelRules(p4info_helper, ingress_sw, egress_sw, tunnel_id,
                     dst_eth_addr, dst_ip_addr, port):
    # 1) Tunnel Ingress Rule
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": (dst_ip_addr, 32)
        },
        action_name="MyIngress.myTunnel_ingress",
        action_params={
            "dst_id": tunnel_id,
        })
    ingress_sw.WriteTableEntry(table_entry)
    print("Installed ingress tunnel rule on %s" % ingress_sw.name)

    # 2) Tunnel Transit Rule
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.myTunnel_exact",
        match_fields={
            "hdr.myTunnel.dst_id": tunnel_id
        },
        action_name="MyIngress.myTunnel_forward",
        action_params={
                    "port":port,
        }
    )
    ingress_sw.WriteTableEntry(table_entry)
    print("TODO Install transit tunnel rule")

    # 3) Tunnel Egress Rule
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.myTunnel_exact",
        match_fields={
            "hdr.myTunnel.dst_id": tunnel_id
        },
        action_name="MyIngress.myTunnel_egress",
        action_params={
            "dstAddr": dst_eth_addr,
            "port": SWITCH_TO_HOST_PORT
        })
    egress_sw.WriteTableEntry(table_entry)
    print("Installed egress tunnel rule on %s" % egress_sw.name)


def readTableRules(p4info_helper, sw):
    #交换机流表规则的读取
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
            #print(entry)
            #print('-----')
            print()


def printCounter(p4info_helper, sw, counter_name, index):
    for response in sw.ReadCounters(p4info_helper.get_counters_id(counter_name), index):
        for entity in response.entities:
            counter = entity.counter_entry
            print("%s %s %d: %d packets (%d bytes)" % (
                sw.name, counter_name, index,
                counter.data.packet_count, counter.data.byte_count
            ))

def main(p4info_file_path, bmv2_file_path):
    # Instantiate a P4Runtime helper from the p4info file
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)

    try:
        #增加了s3的配置
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
        # 增加s3
        s1.MasterArbitrationUpdate()
        s2.MasterArbitrationUpdate()
        s3.MasterArbitrationUpdate()

        # Install the P4 program on the switches
        s1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s1")
        s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s2")
        s3.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s3")

        # Write the rules that tunnel traffic from h1 to h2
        writeTunnelRules(p4info_helper, ingress_sw=s1, egress_sw=s2, tunnel_id=100,
                         dst_eth_addr="08:00:00:00:02:22", dst_ip_addr="10.0.2.2",port=S1_TO_S2_PORT)

        # Write the rules that tunnel traffic from h2 to h1
        writeTunnelRules(p4info_helper, ingress_sw=s2, egress_sw=s1, tunnel_id=200,
                         dst_eth_addr="08:00:00:00:01:11", dst_ip_addr="10.0.1.1",port=S2_TO_S1_PORT)

	# 补充： Write the rules that tunnel traffic from h1 to h3
        writeTunnelRules(p4info_helper, ingress_sw=s1, egress_sw=s3, tunnel_id=300,
                         dst_eth_addr="08:00:00:00:03:33", dst_ip_addr="10.0.3.3",port=S1_TO_S3_PORT)

        # 补充： Write the rules that tunnel traffic from h3 to h1
        writeTunnelRules(p4info_helper, ingress_sw=s3, egress_sw=s1, tunnel_id=400,
                         dst_eth_addr="08:00:00:00:01:11", dst_ip_addr="10.0.1.1",port=S3_TO_S1_PORT)

	# 补充：Write the rules that tunnel traffic from h2 to h3
        writeTunnelRules(p4info_helper, ingress_sw=s2, egress_sw=s3, tunnel_id=500,
                         dst_eth_addr="08:00:00:00:03:33", dst_ip_addr="10.0.3.3",port=S2_TO_S3_PORT)

	# 补充：Write the rules that tunnel traffic from h3 to h2
        writeTunnelRules(p4info_helper, ingress_sw=s3, egress_sw=s2, tunnel_id=600,
                         dst_eth_addr="08:00:00:00:02:22", dst_ip_addr="10.0.2.2",port=S3_TO_S2_PORT)

        # TODO Uncomment the following two lines to read table entries from s1 and s2
        readTableRules(p4info_helper, s1)
        readTableRules(p4info_helper, s2)
        readTableRules(p4info_helper, s3)

        # 每2秒打印一次通过每条链路的数据包的计数情况
        while True:
            sleep(2)
            print('\n----- Reading tunnel counters -----')
            print('\n--s1->s2---')
            printCounter(p4info_helper, s1, "MyIngress.ingressTunnelCounter", 100)
            printCounter(p4info_helper, s2, "MyIngress.egressTunnelCounter", 100)
            print('\n--s2->s1---')
            printCounter(p4info_helper, s2, "MyIngress.ingressTunnelCounter", 200)
            printCounter(p4info_helper, s1, "MyIngress.egressTunnelCounter", 200)
            print('\n--s1->s3---')
            printCounter(p4info_helper, s1, "MyIngress.ingressTunnelCounter", 300)
            printCounter(p4info_helper, s3, "MyIngress.egressTunnelCounter", 300)
            print('\n--s3->s1---')
            printCounter(p4info_helper, s3, "MyIngress.ingressTunnelCounter", 400)
            printCounter(p4info_helper, s1, "MyIngress.egressTunnelCounter", 400)
            print('\n--s2->s3---')
            printCounter(p4info_helper, s2, "MyIngress.ingressTunnelCounter", 500)
            printCounter(p4info_helper, s3, "MyIngress.egressTunnelCounter", 500)
            print('\n--s3->s2---')
            printCounter(p4info_helper, s3, "MyIngress.ingressTunnelCounter", 600)
            printCounter(p4info_helper, s2, "MyIngress.egressTunnelCounter", 600)
    except KeyboardInterrupt:
        print(" Shutting down.")
    except grpc.RpcError as e:
        printGrpcError(e)

    ShutdownAllSwitchConnections()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/advanced_tunnel.p4.p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/advanced_tunnel.json')
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
