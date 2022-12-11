#!/usr/bin/env python3

import random
import unittest
import subprocess
import sys

sys.path.append("gen-py")

from typing import Dict
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol

from client_utils import waitForServer
from container_manager import ContainerManager
from container_manager.ttypes import (
    ContainerState,
    InvalidOperation,
    CreateContainerRequest,
    StartContainerRequest,
    StopContainerRequest,
    DeleteContainerRequest,
    ListContainerRequest,
    ReportContainerStatusRequest,
    ManagerResponse,
    Command,
)


class TestServerAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # start server with no executor on a port
        port = 5050
        cls._serverProc = subprocess.Popen(["/usr/bin/python3", "main.py", "--port", str(port), "--no-executor"])
        # wait for server to be up
        waitForServer(port)
        # Make a client connection and re-use it across the class since
        # we are driving all the state manually
        cls._transport = TSocket.TSocket("localhost", port)
        cls._transport = TTransport.TBufferedTransport(cls._transport)
        protocol = TBinaryProtocol.TBinaryProtocol(cls._transport)
        cls._client = ContainerManager.Client(protocol)
        cls._transport.open()
        return super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        # close client connection
        cls._transport.close()
        # make sure the server is killed
        cls._serverProc.kill()
        return super().tearDownClass()

    def _checkContainerInfos(self, tags: Dict[str, ContainerState], expectedSize: int):
        # request container info for all the keys
        request = ListContainerRequest(tags.keys())
        response = self._client.listContainers(request)
        self.assertIsNotNone(response)
        self.assertEqual(len(response.containerInfos), expectedSize)
        for ctag, expectedState in tags.items():
            # find the container Info and check state
            for info in response.containerInfos:
                if ctag == info.tag:
                    self.assertEqual(expectedState, info.state)

    def _checkAgentResponse(
        self, tag: str, state: ContainerState, expectedResponse: ManagerResponse
    ):
        request = ReportContainerStatusRequest()
        request.tag = tag
        request.state = state
        # the assistent and workload pid isn't that important for this test
        request.pid = random.randint(0, 100)
        request.workloadPid = random.randint(100, 200)
        response = self._client.reportContainerStatus(request)
        self.assertEqual(response.status, expectedResponse)

    def testStateMachine(self):
        """
        Create a monolithic test since we're sharing a server across all tests and
        state matters. Also due to a lack of time, we avoid making an integration framework


        We will manually drive the state machine through various stages without an executor
        NOTE: Before running this test in another window (or in the background) spawn a
        container manager on port 9090 e.g $(python3 main.py --port 9090)
        """

        # empty state should return no container infos
        self._checkContainerInfos({}, 0)

        # create container tests

        ctags = ["one", "two"]
        # try unique requests
        for tag in ctags:
            request = CreateContainerRequest(tag)
            self._client.createContainer(request)

        # test duplicate creation fails
        with self.assertRaises(InvalidOperation):
            self._client.createContainer(request)

        # should have two container infos in the system
        self._checkContainerInfos({}, len(ctags))

        # start ready containers
        for tag in ctags:
            request = StartContainerRequest(tag, Command("/bin/echo", ["howdy"]))
            self._client.startContainer(request)

        # test duplicate start fails
        with self.assertRaises(InvalidOperation):
            self._client.createContainer(request)

        # start non-existent container
        with self.assertRaises(InvalidOperation):
            self._client.startContainer(
                StartContainerRequest("three", Command("/bin/echo", ["howdy"]))
            )

        # should be no running containers yet, as something needs to dequeue
        # and execute them
        response = self._client.getRunningContainers()
        self.assertEqual(len(response.tags), 0)

        # drive their state to running manually
        # it's normally done by the executor and assistent manager

        # should be two containers in ready state
        response = self._client.dequeueReadyContainers()
        self.assertEqual(len(response.tags), len(ctags))

        # should be empty from the previous call
        response = self._client.dequeueReadyContainers()
        self.assertEqual(len(response.tags), 0)

        # if unknown container reporting in, should ask it to ABORT
        self._checkAgentResponse(
            "unknown", ContainerState.RUNNING, ManagerResponse.ABORT
        )

        # transition container one from READY to RUNNING
        self._checkAgentResponse("one", ContainerState.RUNNING, ManagerResponse.OKAY)

        # should be one running container
        response = self._client.getRunningContainers()
        self.assertEqual(len(response.tags), 1)

        # transition container one to DEAD state
        self._checkAgentResponse("one", ContainerState.DEAD, ManagerResponse.OKAY)

        # should also be dead now
        self._checkContainerInfos({"one": ContainerState.DEAD}, 1)

        # should be no running containers now
        response = self._client.getRunningContainers()
        self.assertEqual(len(response.tags), 0)

        # transition container two to RUNNING
        self._checkAgentResponse("two", ContainerState.RUNNING, ManagerResponse.OKAY)

        # stop the second container
        stopRequest = StopContainerRequest("two")
        self._client.stopContainer(stopRequest)

        self._checkContainerInfos({"two": ContainerState.STOPPING}, 1)

        # deleting a stopping/running container should fail
        with self.assertRaises(InvalidOperation):
            self._client.deleteContainer(DeleteContainerRequest("two"))

        # manager should tell us to stop
        self._checkAgentResponse("two", ContainerState.RUNNING, ManagerResponse.STOP)

        # report second container died and manager should now say OKAY
        self._checkAgentResponse("two", ContainerState.DEAD, ManagerResponse.OKAY)

        # should also be dead now
        self._checkContainerInfos({"two": ContainerState.DEAD}, 1)

        # start container not in READY state should fail
        with self.assertRaises(InvalidOperation):
            # container one should be DEAD
            request = StartContainerRequest("one", Command("/bin/echo", ["howdy"]))
            self._client.startContainer(request)

        # delete all containers
        for tag in ctags:
            request = DeleteContainerRequest(tag)
            self._client.deleteContainer(request)

        # an unknown container deletion should fail
        with self.assertRaises(InvalidOperation):
            self._client.deleteContainer(request)

        # should be no container infos any more
        self._checkContainerInfos({}, 0)


if __name__ == "__main__":
    unittest.main()
