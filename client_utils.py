#!/usr/bin/env python3

import sys

sys.path.append("gen-py")

from contextlib import contextmanager

from container_manager import ContainerManager

from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol

@contextmanager
def thriftClient(port):
    transport = TSocket.TSocket("localhost", port)
    transport = TTransport.TBufferedTransport(transport)
    protocol = TBinaryProtocol.TBinaryProtocol(transport)
    client = ContainerManager.Client(protocol)
    try:
        transport.open()
        yield client
    finally:
        transport.close()