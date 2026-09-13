import socket
import ipaddress
import os
import threading
import time
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser, ServiceListener

from .protocol import PortMapping, Protocol


def get_local_ip() -> str:
    """Get the local IP address of this machine on the LAN."""
    configured = os.environ.get('MBT03_BIND_IP', '').strip()
    if configured:
        return str(ipaddress.IPv4Address(configured))
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


class HubRegistrar:
    """
    Registers a single centralized Hub service on the network.
    Advertises a list of available ports to eliminate discovery fragmentation.
    """
    
    def __init__(self, system_id: str = None, log_func=None):
        self.system_id = system_id or 'default'
        self.log = log_func or print
        self.zeroconf = None
        self.service_info = None
        self._registered = False
        
    def update_available(self, available_dict: dict):
        local_ip = get_local_ip()
        if (self._registered and self.service_info is not None
                and self.service_info.parsed_addresses() == [local_ip]
                and self.service_info.properties.get(b'available') ==
                ','.join(f'{pid}:{port}' for pid, port in sorted(available_dict.items())).encode()):
            return
        if self.zeroconf is None:
            self.zeroconf = Zeroconf()
            
        # Format: "1:58435,2:43210"
        ports_str = ",".join(f"{pid}:{port}" for pid, port in sorted(available_dict.items()))
        properties = {
            'system_id': self.system_id,
            'ip': local_ip,
            'available': ports_str
        }
        
        service_name = f"MBT03-Hub-{self.system_id[:8]}.{Protocol.SERVICE_TYPE}"
        
        new_info = ServiceInfo(
            Protocol.SERVICE_TYPE,
            service_name,
            addresses=[socket.inet_aton(local_ip)],
            port=5000, # Dummy port, unused by the actual connection
            properties=properties,
            server=f"mbt03-hub-{self.system_id[:8]}.local.",
        )
        
        try:
            if not self._registered:
                self.zeroconf.register_service(new_info)
                self._registered = True
                self.log(f"[HubRegistrar] Registered Hub: available=[{ports_str}]")
            else:
                self.zeroconf.update_service(new_info)
                self.log(f"[HubRegistrar] Updated Hub: available=[{ports_str}]")
            self.service_info = new_info
        except Exception as e:
            self.log(f"[HubRegistrar] Update failed: {e}")
            
    def close(self):
        if self._registered and self.service_info:
            try:
                self.zeroconf.unregister_service(self.service_info)
            except: pass
        if self.zeroconf:
            try:
                self.zeroconf.close()
            except: pass
            self.zeroconf = None


class ServerFinder(ServiceListener):
    def __init__(self, log_func=None):
        self.log = log_func or print
        self.zeroconf = None
        self.browser = None
        self._lock = threading.Lock()
        
        # Pseudo-servers parsed from Hub records
        self.available_servers = {}
        self._new_server_event = threading.Event()
        self._cancel_event = threading.Event()
    
    def start(self):
        if self.zeroconf is not None:
            return
        self._new_server_event.clear()
        self._cancel_event.clear()
        self.zeroconf = Zeroconf()
        self.browser = ServiceBrowser(self.zeroconf, Protocol.SERVICE_TYPE, self)
        self.log("[Discovery] Started browsing for Hub...")
    
    def stop(self):
        self.cancel()
        browser = self.browser
        self.browser = None
        if browser:
            try:
                browser.cancel()
            except Exception:
                pass
        if self.zeroconf:
            zeroconf = self.zeroconf
            self.zeroconf = None
            try:
                zeroconf.close()
            except Exception:
                pass
    
    def cancel(self):
        self._cancel_event.set()
        self._new_server_event.set()
    
    def add_service(self, zc, type_, name):
        try:
            if "MBT03-Hub" not in name:
                return # Ignore legacy isolated port services if they exist
                
            info = zc.get_service_info(type_, name)
            if info is None:
                return
                
            props = {
                k.decode() if isinstance(k, bytes) else k: 
                v.decode() if isinstance(v, bytes) else v 
                for k, v in info.properties.items()
            }
            
            sys_id = props.get('system_id', 'default')
            addresses = info.parsed_addresses()
            if not addresses:
                return
            ip = addresses[0]
            
            avail_str = props.get('available', '')
            
            # format "1:48392,2:51234"
            avail_ports = {}
            if avail_str:
                for pair in avail_str.split(','):
                    parts = pair.split(':')
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        port_id, port = int(parts[0]), int(parts[1])
                        if port_id in PortMapping.MAP and 1 <= port <= 65535:
                            avail_ports[port_id] = port
            
            with self._lock:
                # Remove stale pseudo-servers for this Hub sys_id
                stale_keys = [k for k, v in self.available_servers.items() if v.get('system_id') == sys_id]
                for k in stale_keys:
                    del self.available_servers[k]
                    
                # Hydrate pseudo-servers for the available ports
                for p_id, p_port in avail_ports.items():
                    p_name = f"Port-{p_id}-{sys_id}"
                    self.available_servers[p_name] = {
                        'ip': ip,
                        'port': p_port,
                        'port_id': p_id,
                        'system_id': sys_id
                    }
                    
            self._new_server_event.set()
            self.log(f"[Discovery] Hub {sys_id[:8]} at {ip} update: {list(avail_ports.keys())}")
        except Exception as e:
            self.log(f"[Discovery] Error parsing Hub '{name}': {e}")
    
    def update_service(self, zc, type_, name):
        self.add_service(zc, type_, name)
    
    def remove_service(self, zc, type_, name):
        with self._lock:
            # We don't extract sys_id easily from name, so just iterate and check if name matches...
            if "MBT03-Hub" in name:
                try:
                    sys_id_target = name.split('-Hub-')[1].split('.')[0]
                except:
                    return
                stale_keys = [k for k, v in self.available_servers.items() if v.get('system_id', '').startswith(sys_id_target)]
                for k in stale_keys:
                    del self.available_servers[k]
                self.log(f"[Discovery] Hub vanished. Wiped pseudo-servers for {sys_id_target}")
    
    def find_all_servers(self, exclude_port_id: int = None, 
                         prefer_system_id: str = None,
                         timeout: float = 30.0,
                         gather_time: float = 0.5) -> list:
        deadline = time.monotonic() + timeout
        first_found_time = None
        
        while time.monotonic() < deadline and not self._cancel_event.is_set():
            self._new_server_event.clear()
            
            with self._lock:
                valid_servers = []
                for name, info in self.available_servers.items():
                    if exclude_port_id is not None and info['port_id'] == exclude_port_id:
                        continue
                    valid_servers.append((info['ip'], info['port'], info['port_id'], info.get('system_id', 'default')))
                
                if valid_servers:
                    if first_found_time is None:
                        first_found_time = time.monotonic()
                    
                    def sort_key(s):
                        sys_match = 0 if (prefer_system_id and s[3] == prefer_system_id) else 1
                        return (sys_match, s[2])
                        
                    valid_servers.sort(key=sort_key)
                    
                    # Wait the full gather_time so we see all ports from the Hub definitively
                    if time.monotonic() - first_found_time >= gather_time:
                        return valid_servers
            
            remaining = deadline - time.monotonic()
            if remaining > 0:
                if self._cancel_event.is_set():
                    return []
                self._new_server_event.wait(min(remaining, Protocol.SEARCH_RETRY_INTERVAL))
        
        return []

    def find_any_server(self, exclude_port_id: int = None, 
                        prefer_system_id: str = None,
                        timeout: float = 30.0):
        servers = self.find_all_servers(exclude_port_id, prefer_system_id, timeout, gather_time=0.5)
        if servers:
            return servers[0]
        return None
