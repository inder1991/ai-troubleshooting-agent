"""OID MIB Registry — 200+ common SNMP OIDs mapped to human-readable names.

Includes standard MIBs (SNMPv2-MIB, IF-MIB, HOST-RESOURCES-MIB, etc.)
and enterprise OIDs from Cisco, Juniper, Palo Alto, Arista, Fortinet, F5, and more.
"""
from __future__ import annotations

MIB_REGISTRY: dict[str, dict] = {
    # ═══════════════════════════════════════════════════════════════
    # SNMPv2-MIB  (1.3.6.1.2.1.1.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.1.1.0": {"name": "sysDescr", "module": "SNMPv2-MIB", "description": "System description"},
    "1.3.6.1.2.1.1.2.0": {"name": "sysObjectID", "module": "SNMPv2-MIB", "description": "Vendor object identifier"},
    "1.3.6.1.2.1.1.3.0": {"name": "sysUpTime", "module": "SNMPv2-MIB", "description": "Uptime in hundredths of seconds"},
    "1.3.6.1.2.1.1.4.0": {"name": "sysContact", "module": "SNMPv2-MIB", "description": "System contact person"},
    "1.3.6.1.2.1.1.5.0": {"name": "sysName", "module": "SNMPv2-MIB", "description": "System name (hostname)"},
    "1.3.6.1.2.1.1.6.0": {"name": "sysLocation", "module": "SNMPv2-MIB", "description": "System physical location"},
    "1.3.6.1.2.1.1.7.0": {"name": "sysServices", "module": "SNMPv2-MIB", "description": "Set of services offered"},
    "1.3.6.1.2.1.1.8.0": {"name": "sysORLastChange", "module": "SNMPv2-MIB", "description": "Last change to sysOR table"},
    "1.3.6.1.2.1.1.9.1.2": {"name": "sysORID", "module": "SNMPv2-MIB", "description": "Object resource OID"},
    "1.3.6.1.2.1.1.9.1.3": {"name": "sysORDescr", "module": "SNMPv2-MIB", "description": "Object resource description"},
    "1.3.6.1.2.1.1.9.1.4": {"name": "sysORUpTime", "module": "SNMPv2-MIB", "description": "Object resource uptime"},

    # ═══════════════════════════════════════════════════════════════
    # IF-MIB  (1.3.6.1.2.1.2.*)  — Interface table
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.2.1.0": {"name": "ifNumber", "module": "IF-MIB", "description": "Number of network interfaces"},
    "1.3.6.1.2.1.2.2.1.1": {"name": "ifIndex", "module": "IF-MIB", "description": "Interface index"},
    "1.3.6.1.2.1.2.2.1.2": {"name": "ifDescr", "module": "IF-MIB", "description": "Interface description"},
    "1.3.6.1.2.1.2.2.1.3": {"name": "ifType", "module": "IF-MIB", "description": "Interface type (IANAifType)"},
    "1.3.6.1.2.1.2.2.1.4": {"name": "ifMtu", "module": "IF-MIB", "description": "Interface MTU size"},
    "1.3.6.1.2.1.2.2.1.5": {"name": "ifSpeed", "module": "IF-MIB", "description": "Interface speed in bits/sec"},
    "1.3.6.1.2.1.2.2.1.6": {"name": "ifPhysAddress", "module": "IF-MIB", "description": "Interface MAC address"},
    "1.3.6.1.2.1.2.2.1.7": {"name": "ifAdminStatus", "module": "IF-MIB", "description": "Admin status (up/down/testing)"},
    "1.3.6.1.2.1.2.2.1.8": {"name": "ifOperStatus", "module": "IF-MIB", "description": "Operational status (up/down)"},
    "1.3.6.1.2.1.2.2.1.9": {"name": "ifLastChange", "module": "IF-MIB", "description": "Last status change time"},
    "1.3.6.1.2.1.2.2.1.10": {"name": "ifInOctets", "module": "IF-MIB", "description": "Inbound octets counter"},
    "1.3.6.1.2.1.2.2.1.11": {"name": "ifInUcastPkts", "module": "IF-MIB", "description": "Inbound unicast packets"},
    "1.3.6.1.2.1.2.2.1.12": {"name": "ifInNUcastPkts", "module": "IF-MIB", "description": "Inbound non-unicast packets"},
    "1.3.6.1.2.1.2.2.1.13": {"name": "ifInDiscards", "module": "IF-MIB", "description": "Inbound discarded packets"},
    "1.3.6.1.2.1.2.2.1.14": {"name": "ifInErrors", "module": "IF-MIB", "description": "Inbound error packets"},
    "1.3.6.1.2.1.2.2.1.15": {"name": "ifInUnknownProtos", "module": "IF-MIB", "description": "Inbound unknown protocol packets"},
    "1.3.6.1.2.1.2.2.1.16": {"name": "ifOutOctets", "module": "IF-MIB", "description": "Outbound octets counter"},
    "1.3.6.1.2.1.2.2.1.17": {"name": "ifOutUcastPkts", "module": "IF-MIB", "description": "Outbound unicast packets"},
    "1.3.6.1.2.1.2.2.1.18": {"name": "ifOutNUcastPkts", "module": "IF-MIB", "description": "Outbound non-unicast packets"},
    "1.3.6.1.2.1.2.2.1.19": {"name": "ifOutDiscards", "module": "IF-MIB", "description": "Outbound discarded packets"},
    "1.3.6.1.2.1.2.2.1.20": {"name": "ifOutErrors", "module": "IF-MIB", "description": "Outbound error packets"},
    "1.3.6.1.2.1.2.2.1.21": {"name": "ifOutQLen", "module": "IF-MIB", "description": "Outbound queue length"},
    "1.3.6.1.2.1.2.2.1.22": {"name": "ifSpecific", "module": "IF-MIB", "description": "Interface specific MIB reference"},

    # IF-MIB ifXTable (high-capacity counters)
    "1.3.6.1.2.1.31.1.1.1.1": {"name": "ifName", "module": "IF-MIB", "description": "Interface short name"},
    "1.3.6.1.2.1.31.1.1.1.6": {"name": "ifHCInOctets", "module": "IF-MIB", "description": "Inbound octets (64-bit)"},
    "1.3.6.1.2.1.31.1.1.1.7": {"name": "ifHCInUcastPkts", "module": "IF-MIB", "description": "Inbound unicast packets (64-bit)"},
    "1.3.6.1.2.1.31.1.1.1.8": {"name": "ifHCInMulticastPkts", "module": "IF-MIB", "description": "Inbound multicast packets (64-bit)"},
    "1.3.6.1.2.1.31.1.1.1.9": {"name": "ifHCInBroadcastPkts", "module": "IF-MIB", "description": "Inbound broadcast packets (64-bit)"},
    "1.3.6.1.2.1.31.1.1.1.10": {"name": "ifHCOutOctets", "module": "IF-MIB", "description": "Outbound octets (64-bit)"},
    "1.3.6.1.2.1.31.1.1.1.11": {"name": "ifHCOutUcastPkts", "module": "IF-MIB", "description": "Outbound unicast packets (64-bit)"},
    "1.3.6.1.2.1.31.1.1.1.12": {"name": "ifHCOutMulticastPkts", "module": "IF-MIB", "description": "Outbound multicast packets (64-bit)"},
    "1.3.6.1.2.1.31.1.1.1.13": {"name": "ifHCOutBroadcastPkts", "module": "IF-MIB", "description": "Outbound broadcast packets (64-bit)"},
    "1.3.6.1.2.1.31.1.1.1.15": {"name": "ifHighSpeed", "module": "IF-MIB", "description": "Interface speed in Mbps"},
    "1.3.6.1.2.1.31.1.1.1.18": {"name": "ifAlias", "module": "IF-MIB", "description": "Interface alias / description"},

    # ═══════════════════════════════════════════════════════════════
    # IP-MIB  (1.3.6.1.2.1.4.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.4.1.0": {"name": "ipForwarding", "module": "IP-MIB", "description": "IP forwarding enabled/disabled"},
    "1.3.6.1.2.1.4.2.0": {"name": "ipDefaultTTL", "module": "IP-MIB", "description": "Default IP TTL value"},
    "1.3.6.1.2.1.4.3.0": {"name": "ipInReceives", "module": "IP-MIB", "description": "Total IP datagrams received"},
    "1.3.6.1.2.1.4.4.0": {"name": "ipInHdrErrors", "module": "IP-MIB", "description": "IP datagrams with header errors"},
    "1.3.6.1.2.1.4.5.0": {"name": "ipInAddrErrors", "module": "IP-MIB", "description": "IP datagrams with address errors"},
    "1.3.6.1.2.1.4.6.0": {"name": "ipForwDatagrams", "module": "IP-MIB", "description": "IP datagrams forwarded"},
    "1.3.6.1.2.1.4.9.0": {"name": "ipInDelivers", "module": "IP-MIB", "description": "IP datagrams delivered locally"},
    "1.3.6.1.2.1.4.10.0": {"name": "ipOutRequests", "module": "IP-MIB", "description": "IP datagrams sent"},
    "1.3.6.1.2.1.4.11.0": {"name": "ipOutDiscards", "module": "IP-MIB", "description": "IP output datagrams discarded"},
    "1.3.6.1.2.1.4.12.0": {"name": "ipOutNoRoutes", "module": "IP-MIB", "description": "IP datagrams with no route"},
    "1.3.6.1.2.1.4.20.1.1": {"name": "ipAdEntAddr", "module": "IP-MIB", "description": "IP address of this entry"},
    "1.3.6.1.2.1.4.20.1.2": {"name": "ipAdEntIfIndex", "module": "IP-MIB", "description": "Interface index for IP address"},
    "1.3.6.1.2.1.4.20.1.3": {"name": "ipAdEntNetMask", "module": "IP-MIB", "description": "Subnet mask for IP address"},
    "1.3.6.1.2.1.4.21.1.1": {"name": "ipRouteDest", "module": "IP-MIB", "description": "Route destination address"},
    "1.3.6.1.2.1.4.21.1.7": {"name": "ipRouteNextHop", "module": "IP-MIB", "description": "Route next hop address"},
    "1.3.6.1.2.1.4.21.1.8": {"name": "ipRouteType", "module": "IP-MIB", "description": "Route type (direct/indirect)"},
    "1.3.6.1.2.1.4.21.1.11": {"name": "ipRouteMetric1", "module": "IP-MIB", "description": "Primary route metric"},

    # ═══════════════════════════════════════════════════════════════
    # TCP-MIB  (1.3.6.1.2.1.6.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.6.1.0": {"name": "tcpRtoAlgorithm", "module": "TCP-MIB", "description": "TCP retransmission timeout algorithm"},
    "1.3.6.1.2.1.6.5.0": {"name": "tcpActiveOpens", "module": "TCP-MIB", "description": "TCP active open connections"},
    "1.3.6.1.2.1.6.6.0": {"name": "tcpPassiveOpens", "module": "TCP-MIB", "description": "TCP passive open connections"},
    "1.3.6.1.2.1.6.7.0": {"name": "tcpAttemptFails", "module": "TCP-MIB", "description": "TCP connection attempt failures"},
    "1.3.6.1.2.1.6.8.0": {"name": "tcpEstabResets", "module": "TCP-MIB", "description": "TCP established connection resets"},
    "1.3.6.1.2.1.6.9.0": {"name": "tcpCurrEstab", "module": "TCP-MIB", "description": "TCP current established connections"},
    "1.3.6.1.2.1.6.10.0": {"name": "tcpInSegs", "module": "TCP-MIB", "description": "TCP segments received"},
    "1.3.6.1.2.1.6.11.0": {"name": "tcpOutSegs", "module": "TCP-MIB", "description": "TCP segments sent"},
    "1.3.6.1.2.1.6.12.0": {"name": "tcpRetransSegs", "module": "TCP-MIB", "description": "TCP retransmitted segments"},

    # ═══════════════════════════════════════════════════════════════
    # UDP-MIB  (1.3.6.1.2.1.7.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.7.1.0": {"name": "udpInDatagrams", "module": "UDP-MIB", "description": "UDP datagrams received"},
    "1.3.6.1.2.1.7.2.0": {"name": "udpNoPorts", "module": "UDP-MIB", "description": "UDP datagrams to non-listening ports"},
    "1.3.6.1.2.1.7.3.0": {"name": "udpInErrors", "module": "UDP-MIB", "description": "UDP datagrams with errors"},
    "1.3.6.1.2.1.7.4.0": {"name": "udpOutDatagrams", "module": "UDP-MIB", "description": "UDP datagrams sent"},

    # ═══════════════════════════════════════════════════════════════
    # SNMP-MIB  (1.3.6.1.2.1.11.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.11.1.0": {"name": "snmpInPkts", "module": "SNMPv2-MIB", "description": "SNMP packets received"},
    "1.3.6.1.2.1.11.2.0": {"name": "snmpOutPkts", "module": "SNMPv2-MIB", "description": "SNMP packets sent"},
    "1.3.6.1.2.1.11.3.0": {"name": "snmpInBadVersions", "module": "SNMPv2-MIB", "description": "SNMP bad version packets"},
    "1.3.6.1.2.1.11.4.0": {"name": "snmpInBadCommunityNames", "module": "SNMPv2-MIB", "description": "SNMP invalid community strings"},
    "1.3.6.1.2.1.11.30.0": {"name": "snmpEnableAuthenTraps", "module": "SNMPv2-MIB", "description": "SNMP authentication trap enable"},

    # ═══════════════════════════════════════════════════════════════
    # HOST-RESOURCES-MIB  (1.3.6.1.2.1.25.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.25.1.1.0": {"name": "hrSystemUptime", "module": "HOST-RESOURCES-MIB", "description": "Host uptime since last boot"},
    "1.3.6.1.2.1.25.1.2.0": {"name": "hrSystemDate", "module": "HOST-RESOURCES-MIB", "description": "Host current date and time"},
    "1.3.6.1.2.1.25.1.5.0": {"name": "hrSystemNumUsers", "module": "HOST-RESOURCES-MIB", "description": "Number of logged-in users"},
    "1.3.6.1.2.1.25.1.6.0": {"name": "hrSystemProcesses", "module": "HOST-RESOURCES-MIB", "description": "Number of running processes"},
    "1.3.6.1.2.1.25.1.7.0": {"name": "hrSystemMaxProcesses", "module": "HOST-RESOURCES-MIB", "description": "Maximum number of processes"},
    "1.3.6.1.2.1.25.2.2.0": {"name": "hrMemorySize", "module": "HOST-RESOURCES-MIB", "description": "Total system memory in KB"},
    "1.3.6.1.2.1.25.2.3.1.1": {"name": "hrStorageIndex", "module": "HOST-RESOURCES-MIB", "description": "Storage table index"},
    "1.3.6.1.2.1.25.2.3.1.2": {"name": "hrStorageType", "module": "HOST-RESOURCES-MIB", "description": "Storage type (RAM/disk/etc.)"},
    "1.3.6.1.2.1.25.2.3.1.3": {"name": "hrStorageDescr", "module": "HOST-RESOURCES-MIB", "description": "Storage description"},
    "1.3.6.1.2.1.25.2.3.1.4": {"name": "hrStorageAllocationUnits", "module": "HOST-RESOURCES-MIB", "description": "Storage allocation unit size"},
    "1.3.6.1.2.1.25.2.3.1.5": {"name": "hrStorageSize", "module": "HOST-RESOURCES-MIB", "description": "Storage total size in units"},
    "1.3.6.1.2.1.25.2.3.1.6": {"name": "hrStorageUsed", "module": "HOST-RESOURCES-MIB", "description": "Storage used in units"},
    "1.3.6.1.2.1.25.3.2.1.1": {"name": "hrDeviceIndex", "module": "HOST-RESOURCES-MIB", "description": "Device table index"},
    "1.3.6.1.2.1.25.3.2.1.2": {"name": "hrDeviceType", "module": "HOST-RESOURCES-MIB", "description": "Device type OID"},
    "1.3.6.1.2.1.25.3.2.1.3": {"name": "hrDeviceDescr", "module": "HOST-RESOURCES-MIB", "description": "Device description"},
    "1.3.6.1.2.1.25.3.2.1.5": {"name": "hrDeviceStatus", "module": "HOST-RESOURCES-MIB", "description": "Device status (running/warning/down)"},
    "1.3.6.1.2.1.25.3.3.1.1": {"name": "hrProcessorFrwID", "module": "HOST-RESOURCES-MIB", "description": "Processor firmware ID"},
    "1.3.6.1.2.1.25.3.3.1.2": {"name": "hrProcessorLoad", "module": "HOST-RESOURCES-MIB", "description": "CPU load percentage (1-min avg)"},
    "1.3.6.1.2.1.25.4.2.1.1": {"name": "hrSWRunIndex", "module": "HOST-RESOURCES-MIB", "description": "Running software index"},
    "1.3.6.1.2.1.25.4.2.1.2": {"name": "hrSWRunName", "module": "HOST-RESOURCES-MIB", "description": "Running software name"},
    "1.3.6.1.2.1.25.4.2.1.4": {"name": "hrSWRunPath", "module": "HOST-RESOURCES-MIB", "description": "Running software path"},
    "1.3.6.1.2.1.25.4.2.1.6": {"name": "hrSWRunType", "module": "HOST-RESOURCES-MIB", "description": "Running software type"},
    "1.3.6.1.2.1.25.4.2.1.7": {"name": "hrSWRunStatus", "module": "HOST-RESOURCES-MIB", "description": "Running software status"},

    # ═══════════════════════════════════════════════════════════════
    # ENTITY-MIB  (1.3.6.1.2.1.47.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.47.1.1.1.1.2": {"name": "entPhysicalDescr", "module": "ENTITY-MIB", "description": "Physical entity description"},
    "1.3.6.1.2.1.47.1.1.1.1.3": {"name": "entPhysicalVendorType", "module": "ENTITY-MIB", "description": "Physical entity vendor OID"},
    "1.3.6.1.2.1.47.1.1.1.1.5": {"name": "entPhysicalClass", "module": "ENTITY-MIB", "description": "Physical entity class (chassis/module/port)"},
    "1.3.6.1.2.1.47.1.1.1.1.7": {"name": "entPhysicalName", "module": "ENTITY-MIB", "description": "Physical entity name"},
    "1.3.6.1.2.1.47.1.1.1.1.8": {"name": "entPhysicalHardwareRev", "module": "ENTITY-MIB", "description": "Hardware revision"},
    "1.3.6.1.2.1.47.1.1.1.1.9": {"name": "entPhysicalFirmwareRev", "module": "ENTITY-MIB", "description": "Firmware revision"},
    "1.3.6.1.2.1.47.1.1.1.1.10": {"name": "entPhysicalSoftwareRev", "module": "ENTITY-MIB", "description": "Software revision"},
    "1.3.6.1.2.1.47.1.1.1.1.11": {"name": "entPhysicalSerialNum", "module": "ENTITY-MIB", "description": "Serial number"},
    "1.3.6.1.2.1.47.1.1.1.1.13": {"name": "entPhysicalModelName", "module": "ENTITY-MIB", "description": "Model name"},

    # ═══════════════════════════════════════════════════════════════
    # BRIDGE-MIB / Q-BRIDGE-MIB
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.17.1.1.0": {"name": "dot1dBaseBridgeAddress", "module": "BRIDGE-MIB", "description": "Bridge MAC address"},
    "1.3.6.1.2.1.17.1.2.0": {"name": "dot1dBaseNumPorts", "module": "BRIDGE-MIB", "description": "Number of bridge ports"},
    "1.3.6.1.2.1.17.1.3.0": {"name": "dot1dBaseType", "module": "BRIDGE-MIB", "description": "Bridge type (transparent/SR/SRT)"},
    "1.3.6.1.2.1.17.4.3.1.1": {"name": "dot1dTpFdbAddress", "module": "BRIDGE-MIB", "description": "MAC forwarding table address"},
    "1.3.6.1.2.1.17.4.3.1.2": {"name": "dot1dTpFdbPort", "module": "BRIDGE-MIB", "description": "MAC forwarding table port"},
    "1.3.6.1.2.1.17.7.1.2.2.1.2": {"name": "dot1qTpFdbPort", "module": "Q-BRIDGE-MIB", "description": "VLAN forwarding table port"},
    "1.3.6.1.2.1.17.7.1.4.3.1.1": {"name": "dot1qVlanStaticName", "module": "Q-BRIDGE-MIB", "description": "VLAN name"},

    # ═══════════════════════════════════════════════════════════════
    # LLDP-MIB (1.0.8802.1.1.2.*)
    # ═══════════════════════════════════════════════════════════════
    "1.0.8802.1.1.2.1.3.7.1.2": {"name": "lldpLocPortId", "module": "LLDP-MIB", "description": "LLDP local port ID"},
    "1.0.8802.1.1.2.1.3.7.1.3": {"name": "lldpLocPortDesc", "module": "LLDP-MIB", "description": "LLDP local port description"},
    "1.0.8802.1.1.2.1.4.1.1.5": {"name": "lldpRemChassisId", "module": "LLDP-MIB", "description": "LLDP remote chassis ID"},
    "1.0.8802.1.1.2.1.4.1.1.7": {"name": "lldpRemPortId", "module": "LLDP-MIB", "description": "LLDP remote port ID"},
    "1.0.8802.1.1.2.1.4.1.1.8": {"name": "lldpRemPortDesc", "module": "LLDP-MIB", "description": "LLDP remote port description"},
    "1.0.8802.1.1.2.1.4.1.1.9": {"name": "lldpRemSysName", "module": "LLDP-MIB", "description": "LLDP remote system name"},
    "1.0.8802.1.1.2.1.4.1.1.10": {"name": "lldpRemSysDesc", "module": "LLDP-MIB", "description": "LLDP remote system description"},

    # ═══════════════════════════════════════════════════════════════
    # OSPF-MIB (1.3.6.1.2.1.14.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.14.1.1.0": {"name": "ospfRouterId", "module": "OSPF-MIB", "description": "OSPF router ID"},
    "1.3.6.1.2.1.14.1.2.0": {"name": "ospfAdminStat", "module": "OSPF-MIB", "description": "OSPF admin status (enabled/disabled)"},
    "1.3.6.1.2.1.14.10.1.1": {"name": "ospfNbrIpAddr", "module": "OSPF-MIB", "description": "OSPF neighbor IP address"},
    "1.3.6.1.2.1.14.10.1.6": {"name": "ospfNbrState", "module": "OSPF-MIB", "description": "OSPF neighbor state (full/init/etc.)"},

    # ═══════════════════════════════════════════════════════════════
    # BGP4-MIB (1.3.6.1.2.1.15.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.15.1.0": {"name": "bgpVersion", "module": "BGP4-MIB", "description": "BGP version number"},
    "1.3.6.1.2.1.15.2.0": {"name": "bgpLocalAs", "module": "BGP4-MIB", "description": "BGP local AS number"},
    "1.3.6.1.2.1.15.3.1.1": {"name": "bgpPeerIdentifier", "module": "BGP4-MIB", "description": "BGP peer identifier"},
    "1.3.6.1.2.1.15.3.1.2": {"name": "bgpPeerState", "module": "BGP4-MIB", "description": "BGP peer state (established/idle/etc.)"},
    "1.3.6.1.2.1.15.3.1.9": {"name": "bgpPeerRemoteAs", "module": "BGP4-MIB", "description": "BGP peer remote AS number"},
    "1.3.6.1.2.1.15.3.1.10": {"name": "bgpPeerInUpdates", "module": "BGP4-MIB", "description": "BGP peer incoming updates"},
    "1.3.6.1.2.1.15.3.1.11": {"name": "bgpPeerOutUpdates", "module": "BGP4-MIB", "description": "BGP peer outgoing updates"},

    # ═══════════════════════════════════════════════════════════════
    # ICMP-MIB
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.5.1.0": {"name": "icmpInMsgs", "module": "IP-MIB", "description": "ICMP messages received"},
    "1.3.6.1.2.1.5.2.0": {"name": "icmpInErrors", "module": "IP-MIB", "description": "ICMP error messages received"},
    "1.3.6.1.2.1.5.8.0": {"name": "icmpInEchos", "module": "IP-MIB", "description": "ICMP echo requests received"},
    "1.3.6.1.2.1.5.9.0": {"name": "icmpInEchoReps", "module": "IP-MIB", "description": "ICMP echo replies received"},
    "1.3.6.1.2.1.5.14.0": {"name": "icmpOutMsgs", "module": "IP-MIB", "description": "ICMP messages sent"},
    "1.3.6.1.2.1.5.21.0": {"name": "icmpOutEchos", "module": "IP-MIB", "description": "ICMP echo requests sent"},

    # ═══════════════════════════════════════════════════════════════
    # DISMAN-EVENT-MIB / SNMP engine
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.6.3.10.2.1.1.0": {"name": "snmpEngineID", "module": "SNMP-FRAMEWORK-MIB", "description": "SNMP engine unique identifier"},
    "1.3.6.1.6.3.10.2.1.2.0": {"name": "snmpEngineBoots", "module": "SNMP-FRAMEWORK-MIB", "description": "SNMP engine boot count"},
    "1.3.6.1.6.3.10.2.1.3.0": {"name": "snmpEngineTime", "module": "SNMP-FRAMEWORK-MIB", "description": "SNMP engine time since boot"},

    # ═══════════════════════════════════════════════════════════════
    # CISCO Enterprise OIDs  (1.3.6.1.4.1.9.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.9.2.1.56.0": {"name": "avgBusy1", "module": "CISCO-PROCESS-MIB", "description": "Cisco CPU busy percentage (1-min avg)"},
    "1.3.6.1.4.1.9.2.1.57.0": {"name": "avgBusy5", "module": "CISCO-PROCESS-MIB", "description": "Cisco CPU busy percentage (5-min avg)"},
    "1.3.6.1.4.1.9.2.1.58.0": {"name": "avgBusy15", "module": "CISCO-PROCESS-MIB", "description": "Cisco CPU busy percentage (15-min avg)"},
    "1.3.6.1.4.1.9.9.109.1.1.1.1.3": {"name": "cpmCPUTotal5sec", "module": "CISCO-PROCESS-MIB", "description": "Cisco CPU utilization (5-sec avg)"},
    "1.3.6.1.4.1.9.9.109.1.1.1.1.4": {"name": "cpmCPUTotal1min", "module": "CISCO-PROCESS-MIB", "description": "Cisco CPU utilization (1-min avg)"},
    "1.3.6.1.4.1.9.9.109.1.1.1.1.5": {"name": "cpmCPUTotal5min", "module": "CISCO-PROCESS-MIB", "description": "Cisco CPU utilization (5-min avg)"},
    "1.3.6.1.4.1.9.9.109.1.1.1.1.6": {"name": "cpmCPUTotal5secRev", "module": "CISCO-PROCESS-MIB", "description": "Cisco CPU utilization revised (5-sec)"},
    "1.3.6.1.4.1.9.9.109.1.1.1.1.7": {"name": "cpmCPUTotal1minRev", "module": "CISCO-PROCESS-MIB", "description": "Cisco CPU utilization revised (1-min)"},
    "1.3.6.1.4.1.9.9.109.1.1.1.1.8": {"name": "cpmCPUTotal5minRev", "module": "CISCO-PROCESS-MIB", "description": "Cisco CPU utilization revised (5-min)"},
    "1.3.6.1.4.1.9.9.48.1.1.1.2": {"name": "ciscoMemoryPoolName", "module": "CISCO-MEMORY-POOL-MIB", "description": "Cisco memory pool name"},
    "1.3.6.1.4.1.9.9.48.1.1.1.5": {"name": "ciscoMemoryPoolUsed", "module": "CISCO-MEMORY-POOL-MIB", "description": "Cisco memory pool bytes used"},
    "1.3.6.1.4.1.9.9.48.1.1.1.6": {"name": "ciscoMemoryPoolFree", "module": "CISCO-MEMORY-POOL-MIB", "description": "Cisco memory pool bytes free"},
    "1.3.6.1.4.1.9.9.13.1.3.1.2": {"name": "ciscoEnvMonTemperatureStatusDescr", "module": "CISCO-ENVMON-MIB", "description": "Cisco environment temperature sensor description"},
    "1.3.6.1.4.1.9.9.13.1.3.1.3": {"name": "ciscoEnvMonTemperatureStatusValue", "module": "CISCO-ENVMON-MIB", "description": "Cisco environment temperature value"},
    "1.3.6.1.4.1.9.9.13.1.3.1.4": {"name": "ciscoEnvMonTemperatureThreshold", "module": "CISCO-ENVMON-MIB", "description": "Cisco environment temperature threshold"},
    "1.3.6.1.4.1.9.9.13.1.3.1.6": {"name": "ciscoEnvMonTemperatureState", "module": "CISCO-ENVMON-MIB", "description": "Cisco environment temperature state"},
    "1.3.6.1.4.1.9.9.13.1.4.1.2": {"name": "ciscoEnvMonFanStatusDescr", "module": "CISCO-ENVMON-MIB", "description": "Cisco fan status description"},
    "1.3.6.1.4.1.9.9.13.1.4.1.3": {"name": "ciscoEnvMonFanState", "module": "CISCO-ENVMON-MIB", "description": "Cisco fan state (normal/warning/critical)"},
    "1.3.6.1.4.1.9.9.13.1.5.1.2": {"name": "ciscoEnvMonSupplyStatusDescr", "module": "CISCO-ENVMON-MIB", "description": "Cisco power supply description"},
    "1.3.6.1.4.1.9.9.13.1.5.1.3": {"name": "ciscoEnvMonSupplyState", "module": "CISCO-ENVMON-MIB", "description": "Cisco power supply state"},
    "1.3.6.1.4.1.9.9.23.1.2.1.1.4": {"name": "cdpCacheAddress", "module": "CISCO-CDP-MIB", "description": "CDP neighbor address"},
    "1.3.6.1.4.1.9.9.23.1.2.1.1.6": {"name": "cdpCacheDeviceId", "module": "CISCO-CDP-MIB", "description": "CDP neighbor device ID"},
    "1.3.6.1.4.1.9.9.23.1.2.1.1.7": {"name": "cdpCacheDevicePort", "module": "CISCO-CDP-MIB", "description": "CDP neighbor port ID"},
    "1.3.6.1.4.1.9.9.23.1.2.1.1.8": {"name": "cdpCachePlatform", "module": "CISCO-CDP-MIB", "description": "CDP neighbor platform"},
    "1.3.6.1.4.1.9.9.46.1.3.1.1.2": {"name": "vtpVlanState", "module": "CISCO-VTP-MIB", "description": "Cisco VLAN state"},
    "1.3.6.1.4.1.9.9.46.1.3.1.1.4": {"name": "vtpVlanName", "module": "CISCO-VTP-MIB", "description": "Cisco VLAN name"},
    "1.3.6.1.4.1.9.9.68.1.2.2.1.2": {"name": "vmVlan", "module": "CISCO-VLAN-MEMBERSHIP-MIB", "description": "Cisco VLAN membership"},
    "1.3.6.1.4.1.9.9.276.1.1.2.1.1": {"name": "cefcFRUPowerOperStatus", "module": "CISCO-ENTITY-FRU-CONTROL-MIB", "description": "Cisco FRU power operational status"},
    "1.3.6.1.4.1.9.9.187.1.2.5.1.6": {"name": "cbgpPeer2State", "module": "CISCO-BGP4-MIB", "description": "Cisco BGP peer state"},
    "1.3.6.1.4.1.9.9.187.1.2.5.1.11": {"name": "cbgpPeer2RemoteAs", "module": "CISCO-BGP4-MIB", "description": "Cisco BGP peer remote AS"},
    "1.3.6.1.4.1.9.9.91.1.1.1.1.4": {"name": "entSensorValue", "module": "CISCO-ENTITY-SENSOR-MIB", "description": "Cisco entity sensor current value"},
    "1.3.6.1.4.1.9.9.91.1.1.1.1.1": {"name": "entSensorType", "module": "CISCO-ENTITY-SENSOR-MIB", "description": "Cisco entity sensor type"},
    "1.3.6.1.4.1.9.9.91.1.1.1.1.5": {"name": "entSensorStatus", "module": "CISCO-ENTITY-SENSOR-MIB", "description": "Cisco entity sensor status"},
    "1.3.6.1.4.1.9.9.500.1.2.1.1.1": {"name": "cswSwitchRole", "module": "CISCO-STACKWISE-MIB", "description": "Cisco StackWise switch role"},
    "1.3.6.1.4.1.9.9.500.1.2.1.1.6": {"name": "cswSwitchState", "module": "CISCO-STACKWISE-MIB", "description": "Cisco StackWise switch state"},

    # ═══════════════════════════════════════════════════════════════
    # Juniper Enterprise OIDs  (1.3.6.1.4.1.2636.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.2636.3.1.13.1.5": {"name": "jnxOperatingCPU", "module": "JUNIPER-MIB", "description": "Juniper CPU utilization percentage"},
    "1.3.6.1.4.1.2636.3.1.13.1.6": {"name": "jnxOperatingISR", "module": "JUNIPER-MIB", "description": "Juniper interrupt service routine utilization"},
    "1.3.6.1.4.1.2636.3.1.13.1.7": {"name": "jnxOperatingDRAMSize", "module": "JUNIPER-MIB", "description": "Juniper DRAM size"},
    "1.3.6.1.4.1.2636.3.1.13.1.8": {"name": "jnxOperatingBuffer", "module": "JUNIPER-MIB", "description": "Juniper buffer utilization percentage"},
    "1.3.6.1.4.1.2636.3.1.13.1.11": {"name": "jnxOperatingMemory", "module": "JUNIPER-MIB", "description": "Juniper memory utilization percentage"},
    "1.3.6.1.4.1.2636.3.1.13.1.15": {"name": "jnxOperating1MinLoadAvg", "module": "JUNIPER-MIB", "description": "Juniper 1-min CPU load average"},
    "1.3.6.1.4.1.2636.3.1.13.1.20": {"name": "jnxOperating5MinLoadAvg", "module": "JUNIPER-MIB", "description": "Juniper 5-min CPU load average"},
    "1.3.6.1.4.1.2636.3.1.13.1.25": {"name": "jnxOperating15MinLoadAvg", "module": "JUNIPER-MIB", "description": "Juniper 15-min CPU load average"},
    "1.3.6.1.4.1.2636.3.1.13.1.7.1": {"name": "jnxOperatingTemp", "module": "JUNIPER-MIB", "description": "Juniper operating temperature"},
    "1.3.6.1.4.1.2636.3.1.13.1.6.1": {"name": "jnxOperatingState", "module": "JUNIPER-MIB", "description": "Juniper operating state"},
    "1.3.6.1.4.1.2636.3.4.1.1.1": {"name": "jnxAlarmDescription", "module": "JUNIPER-ALARM-MIB", "description": "Juniper alarm description"},
    "1.3.6.1.4.1.2636.3.4.2.2.1.0": {"name": "jnxYellowAlarmCount", "module": "JUNIPER-ALARM-MIB", "description": "Juniper yellow alarm count"},
    "1.3.6.1.4.1.2636.3.4.2.3.1.0": {"name": "jnxRedAlarmCount", "module": "JUNIPER-ALARM-MIB", "description": "Juniper red alarm count"},
    "1.3.6.1.4.1.2636.3.5.2.1.4": {"name": "jnxFWCounterPacketCount", "module": "JUNIPER-FIREWALL-MIB", "description": "Juniper firewall counter packet count"},
    "1.3.6.1.4.1.2636.3.5.2.1.5": {"name": "jnxFWCounterByteCount", "module": "JUNIPER-FIREWALL-MIB", "description": "Juniper firewall counter byte count"},
    "1.3.6.1.4.1.2636.3.66.1.2.1.1.6": {"name": "jnxBgpM2PeerState", "module": "JUNIPER-BGP-MIB", "description": "Juniper BGP peer state"},
    "1.3.6.1.4.1.2636.3.66.1.2.1.1.13": {"name": "jnxBgpM2PeerRemoteAs", "module": "JUNIPER-BGP-MIB", "description": "Juniper BGP peer remote AS"},

    # ═══════════════════════════════════════════════════════════════
    # Palo Alto Enterprise OIDs  (1.3.6.1.4.1.25461.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.25461.2.1.2.1.1.0": {"name": "panSysSwVersion", "module": "PAN-COMMON-MIB", "description": "Palo Alto software version"},
    "1.3.6.1.4.1.25461.2.1.2.1.3.0": {"name": "panSysHwVersion", "module": "PAN-COMMON-MIB", "description": "Palo Alto hardware version"},
    "1.3.6.1.4.1.25461.2.1.2.1.4.0": {"name": "panSysSerialNumber", "module": "PAN-COMMON-MIB", "description": "Palo Alto serial number"},
    "1.3.6.1.4.1.25461.2.1.2.3.1.0": {"name": "panSessionUtilization", "module": "PAN-COMMON-MIB", "description": "Palo Alto session utilization percentage"},
    "1.3.6.1.4.1.25461.2.1.2.3.2.0": {"name": "panSessionMax", "module": "PAN-COMMON-MIB", "description": "Palo Alto maximum sessions"},
    "1.3.6.1.4.1.25461.2.1.2.3.3.0": {"name": "panSessionActive", "module": "PAN-COMMON-MIB", "description": "Palo Alto active sessions"},
    "1.3.6.1.4.1.25461.2.1.2.3.4.0": {"name": "panSessionActiveTcp", "module": "PAN-COMMON-MIB", "description": "Palo Alto active TCP sessions"},
    "1.3.6.1.4.1.25461.2.1.2.3.5.0": {"name": "panSessionActiveUdp", "module": "PAN-COMMON-MIB", "description": "Palo Alto active UDP sessions"},
    "1.3.6.1.4.1.25461.2.1.2.3.6.0": {"name": "panSessionActiveICMP", "module": "PAN-COMMON-MIB", "description": "Palo Alto active ICMP sessions"},
    "1.3.6.1.4.1.25461.2.1.2.5.1.0": {"name": "panGPGWUtilizationPct", "module": "PAN-COMMON-MIB", "description": "Palo Alto GlobalProtect gateway utilization"},
    "1.3.6.1.4.1.25461.2.1.2.5.2.0": {"name": "panGPGWUtilizationMaxTunnels", "module": "PAN-COMMON-MIB", "description": "Palo Alto GlobalProtect max tunnels"},
    "1.3.6.1.4.1.25461.2.1.2.5.3.0": {"name": "panGPGWUtilizationActiveTunnels", "module": "PAN-COMMON-MIB", "description": "Palo Alto GlobalProtect active tunnels"},
    "1.3.6.1.4.1.25461.2.1.2.1.19.0": {"name": "panSysCpuMgmt", "module": "PAN-COMMON-MIB", "description": "Palo Alto management plane CPU utilization"},
    "1.3.6.1.4.1.25461.2.1.2.1.20.0": {"name": "panSysCpuData", "module": "PAN-COMMON-MIB", "description": "Palo Alto data plane CPU utilization"},

    # ═══════════════════════════════════════════════════════════════
    # Arista Enterprise OIDs  (1.3.6.1.4.1.30065.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.30065.3.9.1.1.0": {"name": "aristaSwVersion", "module": "ARISTA-SW-IP-FORWARDING-MIB", "description": "Arista EOS software version"},
    "1.3.6.1.4.1.30065.3.12.1.1": {"name": "aristaBgp4V2PeerState", "module": "ARISTA-BGP4V2-MIB", "description": "Arista BGP peer state"},
    "1.3.6.1.4.1.30065.3.12.1.2": {"name": "aristaBgp4V2PeerRemoteAs", "module": "ARISTA-BGP4V2-MIB", "description": "Arista BGP peer remote AS"},
    "1.3.6.1.4.1.30065.3.22.1.1": {"name": "aristaHardwareUtilizationTable", "module": "ARISTA-HARDWARE-UTILIZATION-MIB", "description": "Arista hardware utilization table"},
    "1.3.6.1.4.1.30065.3.22.1.2": {"name": "aristaHardwareUtilizationUsed", "module": "ARISTA-HARDWARE-UTILIZATION-MIB", "description": "Arista hardware resources used"},
    "1.3.6.1.4.1.30065.3.22.1.3": {"name": "aristaHardwareUtilizationFree", "module": "ARISTA-HARDWARE-UTILIZATION-MIB", "description": "Arista hardware resources free"},

    # ═══════════════════════════════════════════════════════════════
    # Fortinet Enterprise OIDs  (1.3.6.1.4.1.12356.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.12356.101.4.1.3.0": {"name": "fgSysCpuUsage", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate CPU usage percentage"},
    "1.3.6.1.4.1.12356.101.4.1.4.0": {"name": "fgSysMemUsage", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate memory usage percentage"},
    "1.3.6.1.4.1.12356.101.4.1.8.0": {"name": "fgSysSesCount", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate session count"},
    "1.3.6.1.4.1.12356.101.4.1.11.0": {"name": "fgSysSesRate1", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate session rate (1-min avg)"},
    "1.3.6.1.4.1.12356.101.4.1.5.0": {"name": "fgSysDiskUsage", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate disk usage percentage"},
    "1.3.6.1.4.1.12356.101.4.1.6.0": {"name": "fgSysDiskCapacity", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate disk total capacity"},
    "1.3.6.1.4.1.12356.101.4.5.3.1.7": {"name": "fgVdNumber", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate virtual domain count"},
    "1.3.6.1.4.1.12356.101.10.112.1.2": {"name": "fgVpnTunEntStatus", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate VPN tunnel status"},
    "1.3.6.1.4.1.12356.101.12.2.2.1.2": {"name": "fgIpSesProto", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate IP session protocol"},
    "1.3.6.1.4.1.12356.101.13.1.1.0": {"name": "fgAvVirusDetected", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate virus detected count"},
    "1.3.6.1.4.1.12356.101.13.2.1.0": {"name": "fgIpsIntrusionsDetected", "module": "FORTINET-FORTIGATE-MIB", "description": "FortiGate IPS intrusions detected"},

    # ═══════════════════════════════════════════════════════════════
    # F5 BIG-IP Enterprise OIDs  (1.3.6.1.4.1.3375.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.3375.2.1.1.2.1.44.0": {"name": "sysStatClientCurConns", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 current client connections"},
    "1.3.6.1.4.1.3375.2.1.1.2.1.45.0": {"name": "sysStatServerCurConns", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 current server connections"},
    "1.3.6.1.4.1.3375.2.1.1.2.1.8.0": {"name": "sysStatClientBytesIn", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 client bytes in"},
    "1.3.6.1.4.1.3375.2.1.1.2.1.10.0": {"name": "sysStatClientBytesOut", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 client bytes out"},
    "1.3.6.1.4.1.3375.2.1.1.2.1.12.0": {"name": "sysStatServerBytesIn", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 server bytes in"},
    "1.3.6.1.4.1.3375.2.1.1.2.1.14.0": {"name": "sysStatServerBytesOut", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 server bytes out"},
    "1.3.6.1.4.1.3375.2.1.7.4.2.1.3": {"name": "sysCpuUsageRatio5s", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 CPU usage ratio (5-sec)"},
    "1.3.6.1.4.1.3375.2.1.7.4.2.1.4": {"name": "sysCpuUsageRatio1m", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 CPU usage ratio (1-min)"},
    "1.3.6.1.4.1.3375.2.1.7.4.2.1.5": {"name": "sysCpuUsageRatio5m", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 CPU usage ratio (5-min)"},
    "1.3.6.1.4.1.3375.2.1.1.2.1.143.0": {"name": "sysStatMemoryTotal", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 total memory"},
    "1.3.6.1.4.1.3375.2.1.1.2.1.144.0": {"name": "sysStatMemoryUsed", "module": "F5-BIGIP-SYSTEM-MIB", "description": "F5 memory used"},
    "1.3.6.1.4.1.3375.2.2.5.1.2.1.1": {"name": "ltmPoolName", "module": "F5-BIGIP-LOCAL-MIB", "description": "F5 pool name"},
    "1.3.6.1.4.1.3375.2.2.5.1.2.1.8": {"name": "ltmPoolActiveMemberCnt", "module": "F5-BIGIP-LOCAL-MIB", "description": "F5 pool active member count"},
    "1.3.6.1.4.1.3375.2.2.5.2.3.1.1": {"name": "ltmPoolMemberNodeName", "module": "F5-BIGIP-LOCAL-MIB", "description": "F5 pool member node name"},
    "1.3.6.1.4.1.3375.2.2.5.2.3.1.19": {"name": "ltmPoolMemberMonitorStatus", "module": "F5-BIGIP-LOCAL-MIB", "description": "F5 pool member monitor status"},
    "1.3.6.1.4.1.3375.2.2.10.1.2.1.3": {"name": "ltmVirtualServName", "module": "F5-BIGIP-LOCAL-MIB", "description": "F5 virtual server name"},
    "1.3.6.1.4.1.3375.2.2.10.1.2.1.9": {"name": "ltmVirtualServEnabled", "module": "F5-BIGIP-LOCAL-MIB", "description": "F5 virtual server enabled state"},

    # ═══════════════════════════════════════════════════════════════
    # CheckPoint Enterprise OIDs  (1.3.6.1.4.1.2620.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.2620.1.1.4.0": {"name": "fwPolicyName", "module": "CHECKPOINT-MIB", "description": "CheckPoint firewall policy name"},
    "1.3.6.1.4.1.2620.1.1.25.3.0": {"name": "fwNumConn", "module": "CHECKPOINT-MIB", "description": "CheckPoint current connections"},
    "1.3.6.1.4.1.2620.1.1.25.4.0": {"name": "fwPeakNumConn", "module": "CHECKPOINT-MIB", "description": "CheckPoint peak connections"},
    "1.3.6.1.4.1.2620.1.6.7.2.1.0": {"name": "multiProcUserTime", "module": "CHECKPOINT-MIB", "description": "CheckPoint multi-processor user time"},
    "1.3.6.1.4.1.2620.1.6.7.2.2.0": {"name": "multiProcSystemTime", "module": "CHECKPOINT-MIB", "description": "CheckPoint multi-processor system time"},
    "1.3.6.1.4.1.2620.1.6.7.2.3.0": {"name": "multiProcIdleTime", "module": "CHECKPOINT-MIB", "description": "CheckPoint multi-processor idle time"},
    "1.3.6.1.4.1.2620.1.6.7.4.3.0": {"name": "fwKmemMemUsedReal", "module": "CHECKPOINT-MIB", "description": "CheckPoint real memory used"},
    "1.3.6.1.4.1.2620.1.6.7.4.4.0": {"name": "fwKmemMemFreeReal", "module": "CHECKPOINT-MIB", "description": "CheckPoint real memory free"},

    # ═══════════════════════════════════════════════════════════════
    # Net-SNMP / UCD-MIB (1.3.6.1.4.1.2021.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.2021.10.1.3.1": {"name": "laLoad1", "module": "UCD-SNMP-MIB", "description": "1-minute CPU load average"},
    "1.3.6.1.4.1.2021.10.1.3.2": {"name": "laLoad5", "module": "UCD-SNMP-MIB", "description": "5-minute CPU load average"},
    "1.3.6.1.4.1.2021.10.1.3.3": {"name": "laLoad15", "module": "UCD-SNMP-MIB", "description": "15-minute CPU load average"},
    "1.3.6.1.4.1.2021.4.2.0": {"name": "memTotalSwap", "module": "UCD-SNMP-MIB", "description": "Total swap space"},
    "1.3.6.1.4.1.2021.4.3.0": {"name": "memAvailSwap", "module": "UCD-SNMP-MIB", "description": "Available swap space"},
    "1.3.6.1.4.1.2021.4.4.0": {"name": "memShared", "module": "UCD-SNMP-MIB", "description": "Shared memory"},
    "1.3.6.1.4.1.2021.4.5.0": {"name": "memTotalReal", "module": "UCD-SNMP-MIB", "description": "Total real memory (RAM)"},
    "1.3.6.1.4.1.2021.4.6.0": {"name": "memAvailReal", "module": "UCD-SNMP-MIB", "description": "Available real memory (RAM)"},
    "1.3.6.1.4.1.2021.4.11.0": {"name": "memTotalFree", "module": "UCD-SNMP-MIB", "description": "Total free memory"},
    "1.3.6.1.4.1.2021.4.14.0": {"name": "memBuffer", "module": "UCD-SNMP-MIB", "description": "Buffer memory"},
    "1.3.6.1.4.1.2021.4.15.0": {"name": "memCached", "module": "UCD-SNMP-MIB", "description": "Cached memory"},
    "1.3.6.1.4.1.2021.9.1.2": {"name": "dskPath", "module": "UCD-SNMP-MIB", "description": "Disk mount path"},
    "1.3.6.1.4.1.2021.9.1.6": {"name": "dskTotal", "module": "UCD-SNMP-MIB", "description": "Disk total size (KB)"},
    "1.3.6.1.4.1.2021.9.1.7": {"name": "dskAvail", "module": "UCD-SNMP-MIB", "description": "Disk available space (KB)"},
    "1.3.6.1.4.1.2021.9.1.8": {"name": "dskUsed", "module": "UCD-SNMP-MIB", "description": "Disk used space (KB)"},
    "1.3.6.1.4.1.2021.9.1.9": {"name": "dskPercent", "module": "UCD-SNMP-MIB", "description": "Disk usage percentage"},
    "1.3.6.1.4.1.2021.11.9.0": {"name": "ssCpuUser", "module": "UCD-SNMP-MIB", "description": "CPU user time percentage"},
    "1.3.6.1.4.1.2021.11.10.0": {"name": "ssCpuSystem", "module": "UCD-SNMP-MIB", "description": "CPU system time percentage"},
    "1.3.6.1.4.1.2021.11.11.0": {"name": "ssCpuIdle", "module": "UCD-SNMP-MIB", "description": "CPU idle time percentage"},
    "1.3.6.1.4.1.2021.11.50.0": {"name": "ssCpuRawUser", "module": "UCD-SNMP-MIB", "description": "Raw CPU user time counter"},
    "1.3.6.1.4.1.2021.11.51.0": {"name": "ssCpuRawNice", "module": "UCD-SNMP-MIB", "description": "Raw CPU nice time counter"},
    "1.3.6.1.4.1.2021.11.52.0": {"name": "ssCpuRawSystem", "module": "UCD-SNMP-MIB", "description": "Raw CPU system time counter"},
    "1.3.6.1.4.1.2021.11.53.0": {"name": "ssCpuRawIdle", "module": "UCD-SNMP-MIB", "description": "Raw CPU idle time counter"},
    "1.3.6.1.4.1.2021.11.54.0": {"name": "ssCpuRawWait", "module": "UCD-SNMP-MIB", "description": "Raw CPU I/O wait time counter"},
    "1.3.6.1.4.1.2021.11.56.0": {"name": "ssCpuRawInterrupt", "module": "UCD-SNMP-MIB", "description": "Raw CPU interrupt time counter"},

    # ═══════════════════════════════════════════════════════════════
    # Aruba / HPE Enterprise OIDs  (1.3.6.1.4.1.14823.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.14823.2.2.1.1.1.9.0": {"name": "wlsxSysXProcessorLoad", "module": "WLSX-SYSTEMEXT-MIB", "description": "Aruba system processor load"},
    "1.3.6.1.4.1.14823.2.2.1.1.1.11.0": {"name": "wlsxSysXMemoryUsedPercent", "module": "WLSX-SYSTEMEXT-MIB", "description": "Aruba system memory usage percentage"},
    "1.3.6.1.4.1.14823.2.2.1.1.3.1.0": {"name": "wlsxSysExtAPCount", "module": "WLSX-SYSTEMEXT-MIB", "description": "Aruba managed AP count"},

    # ═══════════════════════════════════════════════════════════════
    # Dell/EMC Enterprise OIDs  (1.3.6.1.4.1.674.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.674.10892.5.4.200.10.1.2": {"name": "systemStateCPUStatus", "module": "IDRAC-MIB-SMIv2", "description": "Dell iDRAC CPU status"},
    "1.3.6.1.4.1.674.10892.5.4.200.10.1.4": {"name": "systemStateMemoryStatus", "module": "IDRAC-MIB-SMIv2", "description": "Dell iDRAC memory status"},
    "1.3.6.1.4.1.674.10892.5.4.200.10.1.9": {"name": "systemStatePowerSupplyStatus", "module": "IDRAC-MIB-SMIv2", "description": "Dell iDRAC power supply status"},
    "1.3.6.1.4.1.674.10892.5.4.200.10.1.12": {"name": "systemStateCoolingDeviceStatus", "module": "IDRAC-MIB-SMIv2", "description": "Dell iDRAC cooling device status"},
    "1.3.6.1.4.1.674.10892.5.4.200.10.1.24": {"name": "systemStateTemperatureStatus", "module": "IDRAC-MIB-SMIv2", "description": "Dell iDRAC temperature status"},
    "1.3.6.1.4.1.674.10892.5.4.700.20.1.6": {"name": "temperatureProbeReading", "module": "IDRAC-MIB-SMIv2", "description": "Dell iDRAC temperature probe reading"},

    # ═══════════════════════════════════════════════════════════════
    # HP / ProCurve Enterprise OIDs  (1.3.6.1.4.1.11.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.11.2.14.11.5.1.9.6.1.0": {"name": "hpSwitchCpuStat", "module": "HP-SWITCH-MIB", "description": "HP switch CPU utilization"},
    "1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.5": {"name": "hpSwitchMemoryTotal", "module": "HP-SWITCH-MIB", "description": "HP switch total memory"},
    "1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.7": {"name": "hpSwitchMemoryFree", "module": "HP-SWITCH-MIB", "description": "HP switch free memory"},

    # ═══════════════════════════════════════════════════════════════
    # Mikrotik Enterprise OIDs (1.3.6.1.4.1.14988.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.14988.1.1.3.10.0": {"name": "mtxrHlCpuTemperature", "module": "MIKROTIK-MIB", "description": "MikroTik CPU temperature"},
    "1.3.6.1.4.1.14988.1.1.3.11.0": {"name": "mtxrHlBoardTemperature", "module": "MIKROTIK-MIB", "description": "MikroTik board temperature"},
    "1.3.6.1.4.1.14988.1.1.3.12.0": {"name": "mtxrHlVoltage", "module": "MIKROTIK-MIB", "description": "MikroTik voltage"},
    "1.3.6.1.4.1.14988.1.1.3.13.0": {"name": "mtxrHlActiveFan", "module": "MIKROTIK-MIB", "description": "MikroTik active fan"},
    "1.3.6.1.4.1.14988.1.1.3.14.0": {"name": "mtxrHlCpuFrequency", "module": "MIKROTIK-MIB", "description": "MikroTik CPU frequency"},
    "1.3.6.1.4.1.14988.1.1.3.100.1.3": {"name": "mtxrInterfaceTxRate", "module": "MIKROTIK-MIB", "description": "MikroTik interface TX rate"},
    "1.3.6.1.4.1.14988.1.1.3.100.1.4": {"name": "mtxrInterfaceRxRate", "module": "MIKROTIK-MIB", "description": "MikroTik interface RX rate"},

    # ═══════════════════════════════════════════════════════════════
    # Ubiquiti Enterprise OIDs (1.3.6.1.4.1.41112.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.41112.1.6.3.3": {"name": "unifiApSystemModel", "module": "UBNT-UniFi-MIB", "description": "UniFi AP model"},
    "1.3.6.1.4.1.41112.1.6.3.5": {"name": "unifiApSystemUptime", "module": "UBNT-UniFi-MIB", "description": "UniFi AP uptime"},

    # ═══════════════════════════════════════════════════════════════
    # Extreme Networks (1.3.6.1.4.1.1916.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.1916.1.32.1.4.1.5": {"name": "extremeCpuMonitorTotalUtilization", "module": "EXTREME-SOFTWARE-MONITOR-MIB", "description": "Extreme Networks CPU utilization"},
    "1.3.6.1.4.1.1916.1.32.2.2.1.4": {"name": "extremeMemoryMonitorUsage", "module": "EXTREME-SOFTWARE-MONITOR-MIB", "description": "Extreme Networks memory usage"},

    # ═══════════════════════════════════════════════════════════════
    # Brocade / Broadcom (1.3.6.1.4.1.1588.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.1588.2.1.1.1.1.22.0": {"name": "swCpuUsage", "module": "SW-MIB", "description": "Brocade switch CPU usage"},
    "1.3.6.1.4.1.1588.2.1.1.1.26.1.0": {"name": "swMemUsage", "module": "SW-MIB", "description": "Brocade switch memory usage"},
    "1.3.6.1.4.1.1588.2.1.1.1.1.7.0": {"name": "swFirmwareVersion", "module": "SW-MIB", "description": "Brocade firmware version"},

    # ═══════════════════════════════════════════════════════════════
    # Huawei Enterprise OIDs (1.3.6.1.4.1.2011.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.2011.6.3.4.1.2": {"name": "hwEntityCpuUsage", "module": "HUAWEI-ENTITY-EXTENT-MIB", "description": "Huawei CPU usage percentage"},
    "1.3.6.1.4.1.2011.6.3.4.1.3": {"name": "hwEntityMemUsage", "module": "HUAWEI-ENTITY-EXTENT-MIB", "description": "Huawei memory usage percentage"},
    "1.3.6.1.4.1.2011.6.3.4.1.8": {"name": "hwEntityTemperature", "module": "HUAWEI-ENTITY-EXTENT-MIB", "description": "Huawei entity temperature"},

    # ═══════════════════════════════════════════════════════════════
    # Nokia / Alcatel-Lucent (1.3.6.1.4.1.6527.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.4.1.6527.3.1.2.1.1.10": {"name": "tmnxChassisCpuUsage", "module": "TIMETRA-CHASSIS-MIB", "description": "Nokia SR OS CPU usage"},
    "1.3.6.1.4.1.6527.3.1.2.1.1.9": {"name": "tmnxChassisMemoryUsed", "module": "TIMETRA-CHASSIS-MIB", "description": "Nokia SR OS memory used"},
    "1.3.6.1.4.1.6527.3.1.2.1.1.15": {"name": "tmnxChassisTemperature", "module": "TIMETRA-CHASSIS-MIB", "description": "Nokia chassis temperature"},

    # ═══════════════════════════════════════════════════════════════
    # Printer MIB (1.3.6.1.2.1.43.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.43.5.1.1.1": {"name": "prtGeneralConfigChanges", "module": "Printer-MIB", "description": "Printer configuration change count"},
    "1.3.6.1.2.1.43.10.2.1.4.1.1": {"name": "prtMarkerLifeCount", "module": "Printer-MIB", "description": "Printer page count (lifetime)"},
    "1.3.6.1.2.1.43.11.1.1.6.1.1": {"name": "prtMarkerSuppliesDescription", "module": "Printer-MIB", "description": "Printer supply description (toner etc.)"},
    "1.3.6.1.2.1.43.11.1.1.8.1.1": {"name": "prtMarkerSuppliesMaxCapacity", "module": "Printer-MIB", "description": "Printer supply max capacity"},
    "1.3.6.1.2.1.43.11.1.1.9.1.1": {"name": "prtMarkerSuppliesLevel", "module": "Printer-MIB", "description": "Printer supply current level"},

    # ═══════════════════════════════════════════════════════════════
    # UPS-MIB (1.3.6.1.2.1.33.*)
    # ═══════════════════════════════════════════════════════════════
    "1.3.6.1.2.1.33.1.1.1.0": {"name": "upsIdentManufacturer", "module": "UPS-MIB", "description": "UPS manufacturer"},
    "1.3.6.1.2.1.33.1.1.2.0": {"name": "upsIdentModel", "module": "UPS-MIB", "description": "UPS model"},
    "1.3.6.1.2.1.33.1.2.1.0": {"name": "upsBatteryStatus", "module": "UPS-MIB", "description": "UPS battery status"},
    "1.3.6.1.2.1.33.1.2.2.0": {"name": "upsSecondsOnBattery", "module": "UPS-MIB", "description": "UPS seconds on battery"},
    "1.3.6.1.2.1.33.1.2.3.0": {"name": "upsEstimatedMinutesRemaining", "module": "UPS-MIB", "description": "UPS estimated minutes remaining"},
    "1.3.6.1.2.1.33.1.2.4.0": {"name": "upsEstimatedChargeRemaining", "module": "UPS-MIB", "description": "UPS estimated charge remaining (%)"},
    "1.3.6.1.2.1.33.1.2.5.0": {"name": "upsBatteryVoltage", "module": "UPS-MIB", "description": "UPS battery voltage"},
    "1.3.6.1.2.1.33.1.2.6.0": {"name": "upsBatteryCurrent", "module": "UPS-MIB", "description": "UPS battery current"},
    "1.3.6.1.2.1.33.1.2.7.0": {"name": "upsBatteryTemperature", "module": "UPS-MIB", "description": "UPS battery temperature"},
    "1.3.6.1.2.1.33.1.3.3.1.3": {"name": "upsInputVoltage", "module": "UPS-MIB", "description": "UPS input voltage"},
    "1.3.6.1.2.1.33.1.4.1.0": {"name": "upsOutputSource", "module": "UPS-MIB", "description": "UPS output source (normal/battery/bypass)"},
    "1.3.6.1.2.1.33.1.4.4.1.2": {"name": "upsOutputVoltage", "module": "UPS-MIB", "description": "UPS output voltage"},
    "1.3.6.1.2.1.33.1.4.4.1.4": {"name": "upsOutputPower", "module": "UPS-MIB", "description": "UPS output power in watts"},
    "1.3.6.1.2.1.33.1.4.4.1.5": {"name": "upsOutputPercentLoad", "module": "UPS-MIB", "description": "UPS output load percentage"},
}


def lookup_oid(oid: str) -> dict | None:
    """Look up a single OID in the MIB registry.

    Returns the registry entry dict or None if not found.
    """
    return MIB_REGISTRY.get(oid)


def batch_lookup(oids: list[str]) -> dict[str, dict]:
    """Look up multiple OIDs and return only those found.

    Returns a dict mapping OID string -> registry entry for each found OID.
    Unknown OIDs are omitted from the result.
    """
    results: dict[str, dict] = {}
    for oid in oids:
        entry = MIB_REGISTRY.get(oid)
        if entry is not None:
            results[oid] = entry
    return results


def search_oids(query: str) -> list[dict]:
    """Search OIDs by name, description, or module (case-insensitive).

    Returns a list of dicts with an added 'oid' field for each match.
    Empty query returns empty list.
    """
    if not query:
        return []
    q = query.lower()
    results: list[dict] = []
    for oid, info in MIB_REGISTRY.items():
        if (
            q in info.get("name", "").lower()
            or q in info.get("description", "").lower()
            or q in info.get("module", "").lower()
        ):
            results.append({"oid": oid, **info})
    return results
