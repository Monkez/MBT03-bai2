# server_client package
# Zeroconf + ZMQ based server-client handshake system for MBT03
#
# Usage:
#   from server_client.server_core import MBT03ServerCore
#   from server_client.client_core import MBT03ClientCore

from .protocol import PortMapping, Protocol

# Lazy imports to allow client-only or server-only deployments
try:
    from .server_core import MBT03ServerCore
except ImportError:
    pass

try:
    from .client_core import MBT03ClientCore
except ImportError:
    pass
