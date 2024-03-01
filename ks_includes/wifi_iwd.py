import os
import logging
import re
import socket
import threading
from threading import Thread
from queue import Queue
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib

class WifiManager:
    networks_in_supplicant = []
    connected = False
    _stop_loop = False

    def __init__(self, interface, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._callbacks = {
            "connected": [],
            "connecting_status": [],
            "scan_results": [],
            "popup": [],
        }
        self._stop_loop = False
        self.connected = False
        self.connected_ssid = None
        self.event = threading.Event()
        self.initialized = True
        self.interface = interface
        self.networks = {}
        self.supplicant_networks = {}
        self.queue = Queue()
        self.timeout = None
        GLib.idle_add(self.read_psk)
        self.timeout = GLib.timeout_add_seconds(180, self.rescan)


    def add_callback(self, name, callback):
        if name in self._callbacks and callback not in self._callbacks[name]:
            self._callbacks[name].append(callback)

    def add_network(self, ssid, psk):
        for netid in list(self.supplicant_networks):
            if self.supplicant_networks[netid]['ssid'] == ssid:
                # Modify network
                logging.warning("modify")
                return
        netid = None
        for i in list(self.supplicant_networks):
            if self.supplicant_networks[i]['ssid'] == ssid:
                netid = i
                break

        logging.warning("other psk")
        data = subprocess.check_output('iwctl --passphrase %s station %s connect %s' % (psk, self.interface, ssid), shell=True, timeout=15)

        if len(data) > 1:
            logging.warning(data)
            return False


        self.read_psk()
        netid = None
        for i in list(self.supplicant_networks):
            if self.supplicant_networks[i]['ssid'] == ssid:
                netid = i
                break

        if netid is None:
            logging.info("Error adding network")
            return False

        return True

    def callback(self, cb_type, msg):
        if cb_type in self._callbacks:
            for cb in self._callbacks[cb_type]:
                GLib.idle_add(cb, msg)

    def connect(self, ssid):
        netid = None
        for nid, net in self.supplicant_networks.items():
            if net['ssid'] == ssid:
                netid = nid
                break

        if netid is None:
            logging.info("Wifi network is not defined in wpa_supplicant")
            return False

        logging.info(f"Attempting to connect to wifi: {netid}")
        self.callback("connecting_status", f"Attempting to connect to {ssid}")
        try:
            data = subprocess.check_output('iwctl --dont-ask station %s connect %s' % (self.interface, ssid), shell=True, timeout=15)
            if len(data) > 1:
                return False
            GLib.idle_add(self.get_current_wifi_idle_add)
            self.callback("connecting_status", "Connected to %s" % ssid)
        except subprocess.TimeoutExpired as e:
            self.callback("connecting_status", "Connection to %s failed due to timeout." % ssid)
            logging.error("timeout")
            logging.error(e.output)
            return False
        logging.info("done")

    def delete_network(self, ssid):
        netid = None
        for i in list(self.supplicant_networks):
            if self.supplicant_networks[i]['ssid'] == ssid:
                netid = i
                break

        if netid is None:
            logging.debug("Unable to find network in wpa_supplicant")
            return

        data = subprocess.check_output("iwctl known-networks %s forget" % ssid, shell=True, timeout=15)

        if len(data) > 0:
            data = data.decode()
            error = data.split("\n")[0]
            logging.errop(error)
            return
        
        for netid in list(self.supplicant_networks):
            if self.supplicant_networks[netid]['ssid'] == ssid:
                del self.supplicant_networks[netid]
                break

    def get_connected_ssid(self):
        return self.connected_ssid

    def get_current_wifi(self):
        con_ssid = os.popen("iwgetid -r").read().strip()
        con_bssid = os.popen("iwgetid -r -a").read().strip()
        prev_ssid = self.connected_ssid

        if con_ssid != "":
            self.connected = True
            self.connected_ssid = con_ssid
            for ssid, val in self.networks.items():
                self.networks[ssid]['connected'] = ssid == con_ssid
            if prev_ssid != self.connected_ssid:
                for cb in self._callbacks['connected']:
                    args = self.connected_ssid, prev_ssid
                    GLib.idle_add(cb, *args)
            return [con_ssid, con_bssid]
        else:
            logging.info("Resetting connected_ssid")
            self.connected = False
            self.connected_ssid = None
            for ssid, val in self.networks.items():
                self.networks[ssid]['connected'] = False
            if prev_ssid != self.connected_ssid:
                for cb in self._callbacks['connected']:
                    args = self.connected_ssid, prev_ssid
                    GLib.idle_add(cb, *args)
            return None

    def get_current_wifi_idle_add(self):
        logging.warning('get_current_wifi_idle_add')
        self.get_current_wifi()
        return False

    def get_network_info(self, ssid=None, mac=None):
        if ssid is not None and ssid in self.networks:
            return self.networks[ssid]
        if mac is not None and ssid is None:
            for net in self.networks:
                if mac == net['mac']:
                    return net
        return {}

    def get_networks(self):
        return list(self.networks)

    def get_supplicant_networks(self):
        return self.supplicant_networks

    def read_psk(self):
        # iwctl/iwd does not always update itself and sometimes 
        # the networks get stuck if you use known-networks. Therefore
        # we get the actual known ssid list from the psk values in the
        # /var/lib/iwd directory
        # currently only supports psk
        data = subprocess.check_output(['ls /var/lib/iwd/*.psk'], shell=True, timeout=5)
        data = data.decode()

        self.supplicant_networks = {}
        self.networks_in_supplicant = []

        net = data.split('\n')
        for i in range(0, len(net) - 1):
            self.supplicant_networks[i] = {
                "ssid": net[i].replace('.psk', '').replace('/var/lib/iwd/', ''),
                "bssid": "",
                "flags": ""
            }
            self.networks_in_supplicant.append(self.supplicant_networks[i])
        logging.info(self.networks_in_supplicant)

    def rescan(self):
        data = subprocess.check_output("iwctl station %s scan" % self.interface, shell=True, timeout=15)
        GLib.timeout_add(1, self.scan_results)

    def save_wpa_conf(self):
        pass

    def scan_results(self):
        data = subprocess.check_output(['iwlist %s scanning' % self.interface], shell=True, timeout=15)
        new_networks = []
        deleted_networks = list(self.networks)

        data = data.decode()
        results = data.split("Cell")
        results.pop(0)

        aps = []
        for res in results:
            res = res.replace("\n", "|").replace("                    ", "").replace("    ", "")
            match = re.match("^.*Address: ([0-9A-F:]+).*ESSID:([^|]+)\|Protocol:([0-9A-Za-z\.\\s]+)\|Mode:([A-z]+)\|Frequency:([0-9\.\sA-Za-z]+).*\|.*IE: ([0-9A-Za-z:\./\\s]+).*\|.*Signal level=([0-9/]+)", res)
            if match:
                net = {
                    "mac": match[1],
                    "channel": WifiChannels.lookup(match[5].replace('.', '')[:4])[1],
                    "connected": False,
                    "configured": False,
                    "frequency": match[5],
                    "flags": match[6],
                    "signal_level_dBm": match[7].split('/')[0],
                    "ssid": match[2].replace("\"", "")
                }

                if "WPA2" in net['flags']:
                    net['encryption'] = "WPA2"
                elif "WPA" in net['flags']:
                    net['encryption'] = "WPA"
                elif "WEP" in net['flags']:
                    net['encryption'] = "WEP"
                else:
                    net['encryption'] = "off"

                aps.append(net)

        cur_info = self.get_current_wifi()
        self.networks = {}
        for ap in aps:
            self.networks[ap['ssid']] = ap
            if cur_info is not None and cur_info[0] == ap['ssid'] and cur_info[1].lower() == ap['mac'].lower():
                self.networks[ap['ssid']]['connected'] = True

        for net in list(self.networks):
            if net in deleted_networks:
                deleted_networks.remove(net)
            else:
                new_networks.append(net)
        if new_networks or deleted_networks:
            for cb in self._callbacks['scan_results']:
                args = new_networks, deleted_networks
                GLib.idle_add(cb, *args)
            

class WifiChannels:
    @staticmethod
    def lookup(freq: str):
        if freq == '2484':
            return "2.4", "14"
        try:
            freq = float(freq)
        except ValueError:
            return None
        if 2412 <= freq <= 2472:
            return "2.4", str(int((freq - 2407) / 5))
        elif 3657.5 <= freq <= 3692.5:
            return "3", str(int((freq - 3000) / 5))
        elif 4915 <= freq <= 4980:
            return "5", str(int((freq - 4000) / 5))
        elif 5035 <= freq <= 5885:
            return "5", str(int((freq - 5000) / 5))
        elif 6455 <= freq <= 7115:
            return "6", str(int((freq - 5950) / 5))
        else:
            return "?", "?"
