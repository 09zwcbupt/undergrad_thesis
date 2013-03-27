from pox.core import core
import pox
log = core.getLogger()

import pox.openflow.libopenflow_01 as of

from pox.lib.revent import *

import time
from collections import defaultdict
from pox.openflow.discovery import Discovery
from pox.lib.util import dpidToStr
from pox.lib.packet.ipv4 import ipv4     #################
from pox.lib.addresses import EthAddr
from pox.lib.addresses import IPAddr
import datetime
import sys
from pox.lib.packet.ethernet import ethernet

from pox.lib.packet.arp import arp     #################
from pox.lib.packet.dhcp import dhcp    ###############

# Timeout for flows
FLOW_IDLE_TIMEOUT = 10
DHCP_Server = [2,2]
Host_info = {}
Location_to_IP = {}
Temp_table = {}

class HostUp (Event):
  def __init__ (self, connection, in_port, ip, mac):
    Event.__init__(self)
    self.connection = connection
    self.port = in_port
    self.dpid = connection.dpid
    self.ip = ip
    self.mac = mac

class HostDown (Event):
  def __init__ (self, connection, in_port, ip, mac):
    Event.__init__(self)
    self.connection = connection
    self.port = in_port
    self.dpid = connection.dpid
    
class HostStatus(EventMixin):
  _eventMixin_events = set([HostUp, HostDown, ])#set up what to listen
  def __init__(self):
      self.listenTo(core)

  def _handle_GoingUpEvent(self, event):
      self.listenTo(core.openflow)
      log.debug("Up...")

  def _handle_PortStatus (self, event):
    dpid = event.connection.dpid
    inport = event.port
    desc = event.ofp.desc
    self.connection = event.connection
    if desc.state is 1:#it means that the link is down
      if (dpid, inport) in Location_to_IP:
        
        ip = Location_to_IP.pop((dpid, inport))
        #Debug
        if (dpid, inport) in Location_to_IP:
          log.debug ("Error: Target Host is still in Ports_info dictionary!")
        else:
          log.debug ("Success: Delete from Ports_info sucessful!")
        #Debug end

        self.raiseEvent(HostDown, event.connection, ip, Host_info[ip][0])#raise HostDown event
        del Host_info[ip]
        #Debug
        if ip in Host_info:
          log.debug("Error: Target Host info is still in Hosts_info dictionary!")
        else:
          log.debug ("Success: Delete host info from Hosts_info sucessful!")
        #Debug end
            

        
  def _handle_PacketIn (self, event):
    def flood ():
      """ Floods the packet """
      msg = of.ofp_packet_out()
      msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
      msg.buffer_id = event.ofp.buffer_id
      msg.in_port = event.port
      self.connection.send(msg)

      #import pdb    
      #pdb.set_trace()

    def drop ():
      # Kill the buffer
      if event.ofp.buffer_id != -1:
        msg = of.ofp_packet_out()
        msg.buffer_id = event.ofp.buffer_id
        event.ofp.buffer_id = -1 # Mark is dead
        msg.in_port = event.port
        self.connection.send(msg)
        
    dpid = event.connection.dpid
    inport = event.port
    packet = event.parsed  ##############3 parse the event and packet is l2 header
    if packet.type == packet.LLDP_TYPE:
      drop()
      return   
    if isinstance(packet.next, ipv4):############4 whether is ipv4 packet
      if isinstance(packet.next.next,dhcp):  ##############5 whether is dhcp packet
        a = packet.next.next
        if a.op == dhcp.BOOTREQUEST:         
            if ord(a.options[dhcp.MSG_TYPE_OPT]) == 1:
              log.debug("This is DHCP-DISCOVERY message, the mac of host is %s, which comes from %i.%i", str(packet.src),dpid,inport)
              loc = (dpid, inport)
              Temp_table[packet.src] = loc
              msg = of.ofp_packet_out()                  
              msg.data = event.data                  
              msg.actions.append(of.ofp_action_output(port = DHCP_Server[1]))                  
              msg.in_port = inport                  
              switches[DHCP_Server[0]].connection.send(msg)
              log.debug("send to DHCP-Server for DHCPDISCOVERY") 
              return
            elif ord(a.options[dhcp.MSG_TYPE_OPT]) == 3:
              log.debug("This is DHCP-REQUEST message, the mac of host is %s, which comes from %i.%i", str(packet.src),dpid,inport)
              loc = (dpid, event.port)
              Temp_table[packet.src] = loc
              msg = of.ofp_packet_out()                  
              msg.data = event.data                 
              msg.actions.append(of.ofp_action_output(port = DHCP_Server[1]))                  
              msg.in_port = DHCP_Server[0]             
              switches[DHCP_Server[1]].connection.send(msg)
              return

            
        elif a.op == dhcp.BOOTREPLY:
            if ord(a.options[dhcp.MSG_TYPE_OPT]) == 2:
              log.debug("This is DHCP-OFFER message, the mac of host is %s, which comes from %i.%i", str(packet.src),dpid,inport)
              client = Temp_table[a.chaddr]
              msg = of.ofp_packet_out()                  
              msg.data = event.data           
              msg.actions.append(of.ofp_action_output(port = client[1]))                  
              msg.in_port = inport                  
              switches[client[0]].connection.send(msg)
              return
            elif ord(a.options[dhcp.MSG_TYPE_OPT]) == 5:
              log.debug("This is DHCP-ACK message, the mac of host is %s, which comes from %i.%i", str(packet.src),dpid,inport)              
              if Temp_table[a.chaddr] != None:
                loc = Temp_table[a.chaddr]
                Host_info[a.yiaddr] = [a.chaddr,loc]
                Location_to_IP[loc] = a.yiaddr
                self.raiseEvent(HostUp, evnet.connection, a.yiaddr, a.chaddr)
                print 'host up############################'
                client = Temp_table[a.chaddr]
                del Temp_table[a.chaddr] 
                msg = of.ofp_packet_out()                  
                msg.data = event.data             
                msg.actions.append(of.ofp_action_output(port = client[1]))                  
                msg.in_port = inport                  
                switches[client[0]].connection.send(msg)
                return
              else: 
                log.debug(" System error")
            elif ord(a.options[dhcp.MSG_TYPE_OPT]) == 6:
              log.debug("This is DHCP-NACK message, the mac of host is %s, which comes from %i.%i", str(packet.src),dpid,inport)
              del Temp_table[a.chaddr] 
              client = Host_info[packet.next.srcip][1]
              msg = of.ofp_packet_out()                  
              msg.data = packet.pack()                  
              msg.actions.append(of.ofp_action_output(port = inport))                  
              msg.in_port = inport                  
              switches[client[1]].connection.send(msg)
              return
            elif ord(a.options[dhcp.MSG_TYPE_OPT]) == 7:
              log.debug("This is DHCP-RELEASE message, the mac of host is %s, which comes from %i.%i", str(packet.src),dpid,inport)
              loc = Host_info[packet.next.srcip][1]
              self.raiseEvent(HostDown, event.connection, packet.next.srcip, Host_info[packet.next.srcip][0])#raise HostDown event
              del Host_info[packet.next.srcip]
              del Location_to_IP[loc]
              self.raiseEvent(HostDown, event.connection, ip, Host_info[ip][0])#raise HostDown event
              msg = of.ofp_packet_out()                  
              msg.data = packet.pack()                  
              msg.actions.append(of.ofp_action_output(port = DHCP_Server[1]))                  
              msg.in_port = inport                  
              switches[DHCP_Server[0]].connection.send(msg)  
              return
              
    elif isinstance(packet.next, arp):
        b = packet.next      
        #log.debug("%i %i ARP %s %s => %s", dpid, inport,      
         #   {arp.REQUEST:"request",arp.REPLY:"reply"}.get(b.opcode,      
          #  'op:%i' % (b.opcode,)), str(b.protosrc), str(b.protodst))      
        if b.prototype == arp.PROTO_TYPE_IP:        
            if b.hwtype == arp.HW_TYPE_ETHERNET:          
                if b.protosrc != 0:         
                    if b.opcode == arp.REQUEST:
                        loc = (self,event.port)
                        Host_info[b.protosrc] = [packet.src,loc]
                        Location_to_IP[loc] = b.protosrc
                        self.raiseEvent(HostUp, b.protosrc, Host_info[b.protosrc])#raise HostUp event
                        if b.protodst in Host_info:               
                        # We have an answer...                
                        #if not self.arpTable[dpid][a.protodst].isExpired():                  
                        # .. and it's relatively current, so we'll reply ourselves                  
                            r = arp()                  
                            r.hwtype = b.hwtype                  
                            r.prototype = b.prototype                  
                            r.hwlen = b.hwlen                  
                            r.protolen = b.protolen                  
                            r.opcode = arp.REPLY                  
                            r.hwdst = b.hwsrc                  
                            r.protodst = b.protosrc                  
                            r.protosrc = b.protodst                  
                            r.hwsrc = Host_info[b.protodst][0]            
                            e = ethernet(type=packet.type, src=r.hwsrc, dst=b.hwsrc)                  
                            e.set_payload(r)                  
                            #log.debug("%i %i answering ARP for %s" % (dpid, inport,                   
                                #str(r.protosrc)))                  
                            msg = of.ofp_packet_out()                  
                            msg.data = e.pack()                  
                            msg.actions.append(of.ofp_action_output(port = of.OFPP_IN_PORT))                  
                            msg.in_port = inport                  
                            event.connection.send(msg)  
                            ##dst_mac = arpTable[b.protodst].mac
                            ##dst_location = mac_map[MAC1]
                            ##match = of.ofp_match.from_packet(packet)
                            ##self.install_path(dst_location[0], dst_location[1], match, event)
                            #time.sleep(0.1)
                            end = datetime.datetime.now()
                            print end-begin
                            return              
                    else:                
                        drop()                
                        return
            
    if packet.dst.isMulticast():
      #import pdb
      #pdb.set_trace()
      #mac_map[MAC1]=(Switch(),1)
      #mac_map[MAC1]=(self,1)
      #print mac_map
      #print mac_map.keys()
      #print mac_map.values()
      #log.debug("Flood multicast from %s", packet.src)
      #flood()
      #log.debug("drop multicast packet from %s", packet.src)      
      drop()      
      return
    else:
      if packet.dst not in mac_map:
        #import pdbCouldn't
        #pdb.set_trace()
        #mac_map[MAC1]=(Switch(),1)
        #print mac_map
        #print mac_map.keys()
        #print mac_map.values()
        #log.debug("%s unknown -- flooding" % (packet.dst,))
        #flood()
        log.debug("%s unknows -- drop" %(packet.dst)) 
        print mac_map.keys()
        print mac_map.values()
        #print "*********##################****************"
        #print switches

        #print switches.keys()
        #print switches[1]
        #print self.arpTable
        drop()        
        return
      else:
        #print "###############################"        
        #log.debug( "%s is packet's src_mac, access port is %i", packet.src,event.port)        
        re_server_dest = mac_map[packet.dst]        
        match = of.ofp_match.from_packet(packet)        
        self.install_path(re_server_dest[0], re_server_dest[1], match, event)        
        #dest = mac_map[packet.dst]        
        #print packet.dst, "is on", dest       
        #match = of.ofp_match.from_packet(packet)        
        #self.install_path(dest[0], dest[1], match, event)

Host_Status = HostStatus()
def launch():
    core.register(HostStatus, Host_Status)
