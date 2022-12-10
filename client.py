#!/usr/bin/env python

import sys

sys.path.append("gen-py")

from time import sleep

from client_utils import thriftClient

from container_manager.ttypes import (
    Command,
    CreateContainerRequest,
    DeleteContainerRequest,
    StartContainerRequest,
    StopContainerRequest,
)

if __name__ == "__main__":
    with thriftClient(9090) as client:
        request = CreateContainerRequest("one")
        client.createContainer(request)
    
    with thriftClient(9090) as client:
        request = StartContainerRequest()
        request.tag = "one"
        request.command = Command("/bin/sleep", ["infinity"])
        client.startContainer(request)
    
    # wait a little for the container to reach running
    sleep(3)
    
    print("stopping container!")
    with thriftClient(9090) as client:
        request = StopContainerRequest("one")
        client.stopContainer(request)

    # wait a little for container to reach stopping
    sleep(3)
    print("deleting container")
    
    with thriftClient(9090) as client:
        request = DeleteContainerRequest("one")
        client.deleteContainer(request)