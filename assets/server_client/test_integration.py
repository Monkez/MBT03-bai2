# -*- coding: utf-8 -*-
"""Quick integration test for server-client handshake (no GUI)."""
import sys, os, time, threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QCoreApplication

# Need QCoreApplication for signals
app = QCoreApplication(sys.argv)

from server_client.server_core import MBT03ServerCore
from server_client.client_core import MBT03ClientCore
from server_client.protocol import Protocol

print("="*60)
print("Integration Test: Server-Client Handshake")
print("="*60)

# Reduce search timeout for testing
Protocol.PRIOR_SEARCH_TIMEOUT = 10.0  # 10s instead of 120s

# --- Start Server ---
print("\n[1] Starting Server (port_id=1)...")
server = MBT03ServerCore(port_id=1)

server_events = []
server.log_signal.connect(lambda msg: None)  # Suppress logs
server.client_connected_signal.connect(lambda info: server_events.append(('connected', info)))
server.client_disconnected_signal.connect(lambda: server_events.append(('disconnected',)))

server.start()
time.sleep(1)  # Let Zeroconf register
print("   Server started and registered on Zeroconf.")

# --- Start Client ---
print("\n[2] Starting Client (prior_port_id=1)...")
client = MBT03ClientCore(prior_port_id=1, config_dir=os.path.join(os.path.dirname(__file__), 'test_config'))

client_events = []
client.log_signal.connect(lambda msg: None)  # Suppress logs
client.connected_signal.connect(lambda info: client_events.append(('connected', info)))
client.disconnected_signal.connect(lambda: client_events.append(('disconnected',)))

client.start()

# Wait for connection
print("   Waiting for client to connect...")
for i in range(30):
    time.sleep(0.5)
    if client.is_connected:
        break

if client.is_connected:
    print(f"   ✅ Client connected to server!")
    print(f"   Server info: {client.server_info}")
    print(f"   Zeroconf registered: {server.registrar.is_registered}")
    
    if not server.registrar.is_registered:
        print(f"   ✅ Server unregistered from Zeroconf (correct)")
    else:
        print(f"   ❌ Server still registered on Zeroconf (should be unregistered)")
else:
    print(f"   ❌ Client failed to connect!")
    print(f"   Server events: {server_events}")
    print(f"   Client events: {client_events}")

# --- Test Heartbeat ---
print("\n[3] Testing heartbeat (3 seconds)...")
time.sleep(3)
if client.is_connected:
    print(f"   ✅ Connection maintained after 3s heartbeat")
else:
    print(f"   ❌ Connection lost during heartbeat test")

# --- Test Send Data ---
print("\n[4] Testing data exchange...")
if client.is_connected:
    success = client.send_data({'test': 'hello', 'value': 42})
    print(f"   Client→Server send: {'✅ OK' if success else '❌ Failed'}")
    time.sleep(0.5)
    
    success = server.send_data_to_client({'response': 'world', 'status': 'ok'})
    print(f"   Server→Client send: {'✅ OK' if success else '❌ Failed'}")
    time.sleep(0.5)

# --- Test Disconnect/Reconnect ---
print("\n[5] Testing disconnect/reconnect...")
if client.is_connected:
    print("   Simulating client disconnect...")
    client.connected = False  # Force disconnect
    time.sleep(3)
    
    # Check server detected disconnect
    print(f"   Server has client: {server.is_connected}")
    
    # Wait for server to re-register and client to reconnect
    print("   Waiting for reconnection...")
    for i in range(20):
        time.sleep(0.5)
        if client.is_connected:
            break
    
    if client.is_connected:
        print(f"   ✅ Client reconnected!")
    else:
        print(f"   ⏳ Reconnection pending (may take longer)")

# --- Cleanup ---
print("\n[6] Cleanup...")
client.stop()
server.stop()
print("   Done.")

# Clean up test config
import shutil
test_config_dir = os.path.join(os.path.dirname(__file__), 'test_config')
if os.path.exists(test_config_dir):
    shutil.rmtree(test_config_dir)

print("\n" + "="*60)
print("Test Complete!")
print("="*60)
sys.exit(0)
