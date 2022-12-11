#!/usr/bin/env python3

import os
import signal
import sys

sys.path.append("gen-py")

from client_utils import thriftClient, containerInState, waitFor
from container_manager.ttypes import (
    AssistentManagerStatusRequest,
    Command,
    ContainerState,
    CreateContainerRequest,
    DeleteContainerRequest,
    StartContainerRequest,
    StopContainerRequest,
)

""" 
    NOTE: we re-create client every call because we have a single threaded
    thrift server for this toy project and our user API and internal API
    are handled by the same thrift handler, meaning only one entity can
    connect at a time, but there are usually three entities invovled in the 
    life cycle of a container in our design
"""


def containerLifeCycle1():
    """
    Flow through user induced shutdown container life cycle
    """
    print("***Starting user controlled lifecycle!***")
    tag = "container_id_1"
    print(f"creating container '{tag}'!")
    with thriftClient(9090) as client:
        request = CreateContainerRequest(tag)
        client.createContainer(request)

    print(f"starting container '{tag}'!")
    with thriftClient(9090) as client:
        request = StartContainerRequest()
        request.tag = tag
        request.command = Command("/bin/sleep", ["infinity"])
        client.startContainer(request)

    # wait a little for the container to reach running
    assert waitFor(containerInState, 9090, tag, ContainerState.RUNNING, timeout=5)

    print(f"stopping container '{tag}'!")
    with thriftClient(9090) as client:
        request = StopContainerRequest(tag)
        client.stopContainer(request)

    # wait a little for container to reach DEAD
    assert waitFor(containerInState, 9090, tag, ContainerState.DEAD, timeout=5)

    print(f"deleting container '{tag}'!")

    with thriftClient(9090) as client:
        request = DeleteContainerRequest(tag)
        client.deleteContainer(request)


def containerLifeCycle2():
    """
    Flow through 'exited cleanly' life cycle for a container
    """
    print("***Starting natural lifecycle!***")
    tag = "container_id_2"
    print(f"creating container '{tag}'!")
    with thriftClient(9090) as client:
        request = CreateContainerRequest(tag)
        client.createContainer(request)

    print(f"starting container '{tag}'!")
    with thriftClient(9090) as client:
        request = StartContainerRequest()
        request.tag = tag
        # short lived command so container exits naturally
        request.command = Command("/bin/sleep", ["1"])
        client.startContainer(request)

    # wait a little for container to reach DEAD
    assert waitFor(containerInState, 9090, tag, ContainerState.DEAD, timeout=5)

    print(f"deleting container '{tag}'!")

    with thriftClient(9090) as client:
        request = DeleteContainerRequest(tag)
        client.deleteContainer(request)


if __name__ == "__main__":
    containerLifeCycle1()
    containerLifeCycle2()
