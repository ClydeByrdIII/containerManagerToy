#!/usr/bin/env python3
import sys

sys.path.append("gen-py")

from typing import List

from container_manager.ttypes import (
    AssistentManagerInfo,
    ContainerInfo,
    ContainerState,
    ContainerIdResponse,
    InvalidOperation,
    CreateContainerRequest,
    StartContainerRequest,
    StopContainerRequest,
    DeleteContainerRequest,
    ListContainerRequest,
    ListContainerResponse,
    ReportContainerStatusRequest,
    ReportContainerStatusResponse,
    AssistentManagerStatusResponse,
    AssistentManagerStatusRequest,
    ManagerResponse,
)

class ContainerManagerHandler:
    """
    API Handler of the container manager thrift service

    This is the API to drive the state machine of a container,
    moving it from the various container states
    
    A cli user/scheduler will use create/start/list/stop/delete calls
    The assistent container manager will only use get/report status calls

    An assumption at the moment is that the thrift server is a single threaded
    server thus avoiding many complex state management issues that one would see
    in a real implementation

    Additionally we are leaving all process killing/management up to the assistent
    container manager. This is problematic due to the many non-user induced events
    on a system that could kill or make unresponsive, the assistent manager
    (e.g bugs, kernel oom killer, D state processes, or resource starvation) thus
    in this implementation the container manager would be ignorant of LOST containers

    Exercises:
    1) [medium-hard] Modify the handler for concurrency
    2) [easy] Persist in memory objects some where (such as rocksdb)
    As is, when the container manager restarts all existing containers will be
    unmanaged and on next status report will be asked to ABORT
    3) [easy] If an assistent manager doesn't report back after a certain period
    of time, consider it LOST
    4) [easy] API transactions aren't secure; We should use ssl
    5) [easy] executor/assistent manager functions should be in a separate
    Handler/server (thread if not in python) and we should be using unix domain
    sockets for communication between the local entities
    """

    def __init__(self):
        # container state accounting
        self.containerInfos = {}
        # assistent managers setup and babysit the container workload
        self.assistentManagers = {}
        # the executor process will pull from this queue and start
        # assistent managers
        self.runnable = []
        # active container accounting
        self.runningContainers = set()

    def _tag_exists(self, tag: str):
        return tag in self.containerInfos

    def _checkDuplicates(self, tag: str):
        if self._tag_exists(tag):
            raise InvalidOperation(f"container: {tag} already exists!")

    def _checkExists(self, tag: str):
        if not self._tag_exists(tag):
            raise InvalidOperation(f"container: {tag} does not exist")

    def _checkInStates(self, tag: str, states: List[ContainerState]):
        if self.containerInfos[tag].state not in states:
            raise InvalidOperation(
                f"container: {tag} state mismatch: Expected {states}, Actual {self.containerInfos[tag].state}"
            )

    """ API for cli user / scheduler """

    def createContainer(self, request: CreateContainerRequest):
        """
        Public:
        Create initial container metadata in the manager
        
        State transitions:
        The container state goes from unknown -> READY
            
        Internal Notes:
        For this implementation, we keep it simple, but things such as container
        filesystem preparation could go here
        """
        self._checkDuplicates(request.tag)
        # initialize container info to the ready state
        self.containerInfos[request.tag] = ContainerInfo(
            request.tag, ContainerState.READY
        )

    def startContainer(self, request: StartContainerRequest):
        """
        Public:
        Enqueue the container to the runnable queue, where later an executor
        will dequeue the container and start it. The user will have to poll
        until the container is in a running state, if the user cares to know.
        
        State Transitions:
        The container state does not change
        The container is made runnable though, which means it's eligible to be
        transitioned to running.
        
        Internal Notes:
        A consequence of our single threaded server handling both user APIs and
        executor/assistent APIs setup is that our server can't respond to an 
        executor/assistent thrift call if the server is stuck waiting on this
        thrift call to complete, so we go with an asynchronous model of work deferral
        """
        # container info must exist and be ready
        self._checkExists(request.tag)
        self._checkInStates(request.tag, [ContainerState.READY])
        # should not be possible for assistent manager to exist at this point
        assert request.tag not in self.assistentManagers
        # create assistent manager object with empty run state (no pid or workload pid)
        self.assistentManagers[request.tag] = AssistentManagerInfo(
            request.tag, request.command
        )
        # enqueue on runnable queue for executor to grab
        self.runnable.append(request.tag)

    def stopContainer(self, request: StopContainerRequest):
        """
        Public:
        Start container shutdown procedure. The user will have to poll
        until the container is in a DEAD state, if the user cares to know

        State transitions:
        The container state transitions from (running/stopping) -> stopping

        Internal Notes:
        same as StartContainer's

        Exercises:
        1) Add an option to ungracefully kill the container cgroup; much easier
        if your kernel supports cgroup.kill https://lwn.net/Articles/855924/, but doable
        in a more annoying way otherwise
        """
        # container info must exist and be running (and thus have an assistent manager)
        self._checkExists(request.tag)
        self._checkInStates(
            request.tag, [ContainerState.STOPPING, ContainerState.RUNNING]
        )
        # mark the container in stopping state
        self.containerInfos[request.tag].state = ContainerState.STOPPING

    def deleteContainer(self, request: DeleteContainerRequest):
        """
        Public:
        Erase the container from container manager memory

        State transitions:
        The container state transitions from (ready/dead/lost) -> unknown
        """
        self._checkExists(request.tag)
        if self.containerInfos[request.tag].state in [
            ContainerState.RUNNING,
            ContainerState.STOPPING,
        ]:
            raise InvalidOperation(f"container {request.tag} is still active!")

        del self.containerInfos[request.tag]
        if request.tag in self.assistentManagers:
            del self.assistentManagers[request.tag]

    def listContainers(self, request: ListContainerRequest) -> ListContainerResponse:
        """
        If tags is None or length 0, return all container infos
        otherwise return container infos corresponding to tags
        """
        if not request.tags or len(request.tags) < 1:
            return ListContainerResponse(self.containerInfos.values())
        for tag in request.tags:
            self._checkExists(tag)
        return ListContainerResponse([self.containerInfos[tag] for tag in request.tags])

    """ API for executor and assistent manager """

    def dequeueReadyContainers(self) -> List[str]:
        """
        Return all the ready container tags and clear the runnable queue.
        This is expected to be called by the executor only
        """
        elements = self.runnable[:]
        self.runnable.clear()
        return ContainerIdResponse(elements)

    def getRunningContainers(self) -> List[str]:
        """
        Return all running container tags
        """
        return ContainerIdResponse(list(self.runningContainers))

    def getAssistentManagerStatus(
        self, request: AssistentManagerStatusRequest
    ) -> AssistentManagerStatusResponse:
        """
        Return info about assistentManager if it's managed
        If it's not managed, return empty response indicating that the
        caller (a rogue assistent manager) should exit immediately
        """
        response = AssistentManagerStatusResponse()
        if request.tag in self.assistentManagers:
            response.amInfo = self.assistentManagers[request.tag]
        return response

    def reportContainerStatus(
        self, request: ReportContainerStatusRequest
    ) -> ReportContainerStatusResponse:
        """
        The assistent container manager will report to the container manager
        the current status of the container

        The container manager will respond what state the assistent manager
        should be in

        The assistent manager will be responsible for killing the workload and itself
        The container manager in this instance will just update metadata

        State transitions:
        The container state transitions among
        ready -> running
        OR
        stopping -> dead
        OR
        running -> dead
        """
        if request.tag not in self.containerInfos:
            # this assistent manager is LOST/not managed and should be killed
            return ReportContainerStatusResponse(ManagerResponse.ABORT)

        if (
            request.state == ContainerState.RUNNING
            and self.containerInfos[request.tag].state == ContainerState.READY
        ):
            # transitioning from ready -> running
            # update assistent manager run time metadata info
            amInfo = self.assistentManagers[request.tag]
            amInfo.pid = request.pid
            amInfo.workloadPid = request.workloadPid
            # update container info metadata
            self.containerInfos[request.tag].state = ContainerState.RUNNING
            self.runningContainers.add(request.tag)
        elif request.state == ContainerState.DEAD:
            # transitioning from stopping/running -> dead
            # preserve assistent manager metadata as it's good for debugging
            # update container info metadata
            self.containerInfos[request.tag].state = ContainerState.DEAD
            self.containerInfos[request.tag].exitInfo = request.exitInfo
            self.runningContainers.remove(request.tag)

        # tell assistent manager to stop the container if it was requested
        if self.containerInfos[request.tag].state == ContainerState.STOPPING:
            response = ReportContainerStatusResponse(ManagerResponse.STOP)
        else:
            response = ReportContainerStatusResponse(ManagerResponse.OKAY)
        return response
