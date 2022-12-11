#!/usr/bin/env python3

import sys
import time

sys.path.append("gen-py")

from contextlib import contextmanager

from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol

from container_manager import ContainerManager
from container_manager.ttypes import ContainerState, ListContainerRequest


@contextmanager
def thriftClient(port: int):
    """
    Context manager to safely provide a thrift client that attempts to clean
    itself up on failures
    """
    transport = TSocket.TSocket("localhost", port)
    transport = TTransport.TBufferedTransport(transport)
    protocol = TBinaryProtocol.TBinaryProtocol(transport)
    client = ContainerManager.Client(protocol)
    try:
        transport.open()
        yield client
    finally:
        transport.close()


def containerInState(port: int, tag: str, state: ContainerState) -> bool:
    """
    Query container manager for state of a container and check if it's
    in the desired state
    """
    with thriftClient(port) as client:
        request = ListContainerRequest([tag])
        response = client.listContainers(request)
        info = response.containerInfos[0]
        return info.state == state


def waitFor(condition, *args, timeout=5, **kwargs) -> bool:
    """
    Wait for up to timeout seconds for the condition function to be satisfied
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition(*args, **kwargs):
            return True
        time.sleep(0.5)
    return False


def isServerUp(port) -> bool:
    """
    Try to establish a connection with the server
    if server isn't up an exeception will be thrown
    """
    try:
        with thriftClient(port) as client:
            # server is up
            return True
    except Exception as e:
        # server is not up
        pass
    return False


def waitForServer(port, timeout=5) -> None:
    """ 
        raise an exception if server is not up within timeout
    """
    if not waitFor(isServerUp, port, timeout=5):
        raise Exception(f"Server is not up after {timeout} seconds!")
