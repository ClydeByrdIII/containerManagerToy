#!/usr/bin/env python3

import unittest
import sys

sys.path.append("gen-py")

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

from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol

class TestServerAPI(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls) -> None:
        # Make socket
        cls._transport = TSocket.TSocket("localhost", 9090)
        # Buffering is critical. Raw sockets are very slow
        cls._transport = TTransport.TBufferedTransport(cls._transport)
        # Wrap in a protocol
        protocol = TBinaryProtocol.TBinaryProtocol(cls._transport)
        # Create a client to use the protocol encoder
        cls._client = ContainerManager.Client(protocol)
        # Connect!
        cls._transport.open()
        return super().setUpClass()
    
    @classmethod
    def tearDownClass(cls) -> None:
        cls._transport.close()
        return super().tearDownClass()
    
    def testIntegration(self):
        """
        Create a monolithic test since we're sharing a server across all tests and
        state matters. Also due to a lack of time, we avoid making an integration framework
        
        
        We will manually drive the state machine through various stages
        """
        
        # empty state should return no container infos
        request = ListContainerRequest()
        response = self._client.listContainers(request)
        self.assertIsNotNone(response)
        self.assertEqual(len(response.containerInfos), 0)
        # create container tests
        
        # try unique request
        request = CreateContainerRequest("one")
        self._client.createContainer(request)
        
        # test duplicate fails
        with self.assertRaises(InvalidOperation):
            self._client.createContainer(request)
        
        # create second container
        self._client.createContainer(CreateContainerRequest("two"))
        
        # should have two container infos
        request = ListContainerRequest()
        response = self._client.listContainers(request)
        self.assertIsNotNone(response)
        self.assertEqual(len(response.containerInfos), 2)
        
        # start ready containers
        request = StartContainerRequest()
        request.tag = "one"
        request.command = Command("/bin/echo", ["howdy"])
        self._client.startContainer(request)
        request.tag = "two"
        self._client.startContainer(request)
        # start non-existent container    
        request.tag = "three"
        with self.assertRaises(InvalidOperation):
            self._client.startContainer(request)
        
        # drive their state to running manually
        # it's normally done by the executor and assistent manager
        
        # should be no running containers yet, as something needs to dequeue
        # and execute them
        response = self._client.getRunningContainers()
        self.assertEqual(len(response.tags), 0)
        
        # should be two containers in ready state
        response = self._client.dequeueReadyContainers()
        self.assertEqual(len(response.tags), 2)
        
        # should be empty this time around
        response = self._client.dequeueReadyContainers()
        self.assertEqual(len(response.tags), 0)
        
        # if unknown container reporting in, should ABORT
        request = ReportContainerStatusRequest()
        request.tag = "unknown"
        request.state = ContainerState.RUNNING
        request.pid = 100
        request.workloadPid = 200
        response = self._client.reportContainerStatus(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status, ManagerResponse.ABORT)
        
        # start one container
        request = ReportContainerStatusRequest()
        request.tag = "one"
        request.state = ContainerState.RUNNING
        request.pid = 100
        request.workloadPid = 200
        response = self._client.reportContainerStatus(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status, ManagerResponse.OKAY)
        
        # should be one running container
        response = self._client.getRunningContainers()
        self.assertEqual(len(response.tags), 1)
        
        # report that it died
        request.state = ContainerState.DEAD
        response = self._client.reportContainerStatus(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status, ManagerResponse.OKAY)
        
        # should be no running containers
        response = self._client.getRunningContainers()
        self.assertEqual(len(response.tags), 0)
        
        # should also be dead now
        request = ListContainerRequest(["one"])
        response = self._client.listContainers(request)
        self.assertIsNotNone(response)
        self.assertEqual(len(response.containerInfos), 1)
        info = response.containerInfos.pop()
        self.assertEqual(info.state, ContainerState.DEAD)
        
        
        # start second container
        request = ReportContainerStatusRequest()
        request.tag = "two"
        request.state = ContainerState.RUNNING
        request.pid = 300
        request.workloadPid = 400
        response = self._client.reportContainerStatus(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status, ManagerResponse.OKAY)
        
        # stop the second container
        stopRequest = StopContainerRequest("two")
        self._client.stopContainer(stopRequest)
        
        # deleting a stopping/running container should fail
        with self.assertRaises(InvalidOperation):
            self._client.deleteContainer(DeleteContainerRequest("two"))
        
        # manager should tell us to stop
        request.state = ContainerState.RUNNING
        response = self._client.reportContainerStatus(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status, ManagerResponse.STOP)
        
        # report second container died
        request.state = ContainerState.DEAD
        response = self._client.reportContainerStatus(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status, ManagerResponse.OKAY)
    
        # should also be dead now
        request = ListContainerRequest(["two"])
        response = self._client.listContainers(request)
        self.assertIsNotNone(response)
        self.assertEqual(len(response.containerInfos), 1)
        info = response.containerInfos.pop()
        self.assertEqual(info.state, ContainerState.DEAD)
        
        # start container not in READY state should fail
        with self.assertRaises(InvalidOperation):
            request = StartContainerRequest()
            request.tag = "one"
            request.command = Command("/bin/echo", ["howdy"])
            self._client.startContainer(request)
        
        # delete both containers
        request = DeleteContainerRequest("one")
        self._client.deleteContainer(request)
        request.tag = "two"
        self._client.deleteContainer(request)
        
        with self.assertRaises(InvalidOperation):
            request.tag = "three"
            self._client.deleteContainer(request)
        
        # should be no container infos anymore
        request = ListContainerRequest()
        response = self._client.listContainers(request)
        self.assertIsNotNone(response)
        self.assertEqual(len(response.containerInfos), 0)
          

if __name__ == '__main__':
    unittest.main()
    