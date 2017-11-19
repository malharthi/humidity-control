
# Some code in this file is from:
#   
#   * https://github.com/softScheck/tplink-smartplug
#   * https://github.com/GadgetReactor/pyHS100

import socket
import json
import logging

SMARTPLUG_PORT = 9999

"""Predefined Smart Plug Commands
For a full list of commands, consult tplink_commands.txt
"""
commands = {'info'     : '{"system":{"get_sysinfo":{}}}',
            'on'       : '{"system":{"set_relay_state":{"state":1}}}',
            'off'      : '{"system":{"set_relay_state":{"state":0}}}',
            'cloudinfo': '{"cnCloud":{"get_info":{}}}',
            'wlanscan' : '{"netif":{"get_scaninfo":{"refresh":0}}}',
            'time'     : '{"time":{"get_time":{}}}',
            'schedule' : '{"schedule":{"get_rules":{}}}',
            'countdown': '{"count_down":{"get_rules":{}}}',
            'antitheft': '{"anti_theft":{"get_rules":{}}}',
            'reboot'   : '{"system":{"reboot":{"delay":1}}}',
            'reset'    : '{"system":{"reset":{"delay":1}}}'
}

def validIP(ip):
    """Check if IP is valid"""
    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except socket.error:
        return False

# Encryption and Decryption of TP-Link Smart Home Protocol
# XOR Autokey Cipher with starting key = 171
def encrypt(string):
    key = 171
    result = "\0\0\0\0"
    for i in string: 
        a = key ^ ord(i)
        key = a
        result += chr(a)
    return result

def decrypt(string):
    key = 171 
    result = ""
    for i in string: 
        a = key ^ ord(i)
        key = ord(i) 
        result += chr(a)
    return result

class SmartPlug(object):
    """Represnts TP-Link HS100 Smart Plug"""
    
    def __init__(self, ip, sysinfo):
        self.ip = ip
        self.sysinfo = sysinfo

    
    def _sendCommand(self, cmd):
        """Send a command and receive the response."""
        reponse = None
        try:
            sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock_tcp.connect((self.ip, SMARTPLUG_PORT))
            sock_tcp.send(encrypt(cmd))
            data = sock_tcp.recv(2048)
            sock_tcp.close()
            
            response = decrypt(data[4:])
        except socket.error as e:
            logging.error('_sendCommand error. socket.error: %s', e)

        return reponse

    def turnOn(self):
        return self._processOnOffResponse(self._sendCommand(commands['on']))

    def turnOff(self):
        return self._processOnOffResponse(self._sendCommand(commands['off']))

    def _processOnOffResponse(self, response):
        info = json.loads(response)
        if "system" in info and "set_relay_state" in info["system"]:
            relayState = info["system"]["set_relay_state"]
            return relayState['err_code'] == 0
        else:
            return False

    def alias(self):
        return self.sysinfo['alias']

def discoverPlugs(timeout=3):
    discovery_query = {"system": {"get_sysinfo": None},
                       "emeter": {"get_realtime": None}}

    broadcastAddr = "255.255.255.255"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)

    request = json.dumps(discovery_query)

    encrypted_req = encrypt(request)
    sock.sendto(encrypted_req[4:], (broadcastAddr, SMARTPLUG_PORT))

    devices = {}

    try:
        while True:
            data, addr = sock.recvfrom(4096)
            ip, port = addr
            info = json.loads(decrypt(data))
            if "system" in info and "get_sysinfo" in info["system"]:
                sysinfo = info["system"]["get_sysinfo"]
                deviceType = sysinfo.get('type')
                if deviceType and 'smartplug' in deviceType.lower():
                    devices[ip] = SmartPlug(ip, sysinfo)
    except socket.timeout:
        pass
    except Exception as ex:
        logging.error("discovery error. %s", ex)

    return devices

    