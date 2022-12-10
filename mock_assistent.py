#!/usr/bin/env python3

import argparse
import os
import signal
import subprocess
import sys

sys.path.append("gen-py")

from time import sleep

from client_utils import thriftClient

from container_manager.ttypes import (
    ReportContainerStatusRequest,
    AssistentManagerStatusRequest,
    ManagerResponse,
    ExitCode,
    ExitInfo,
    ContainerState,
)


def amLog(tag, msg):
    print(f"Assistent Manager ({tag}): {msg}")


class Assistent:
    """
    The purpose of the Assistent Container Manager is to perform container
    set up and monitoring on behalf of the container manager. If the container
    manager dies, the assistent manager will still be alive and happily report
    back to the container manager when the container manager comes back online

    The various things it can do:
    1) log handling for the container
    2) ulimit configuration for the container
    3) cgroup manipulation of the container
    4) mounting for the container
    5) exit status / oom checking of the container
    6) stack trace searching when container exits uncleanly
    7) much, much more

    As this is written in python rather than a more desirable language
    like go/c++/c/rust, it's non-trivial to use system calls like clone(2)
    so this doesn't spawn a "true" container, but it gets the container management
    fundamentals across

    Excercise:
    1) Support all of the above
    2) support using clone(2) (possibly via c++/go/rust rewrite)
    """

    def __init__(self, port: int, tag: str):
        # port for container manager
        self.port = port
        # identifier for assistent and container
        self.tag = tag
        # pid of container workload
        self.cpid = None
        # get container setup info from manager
        self.info = None

        try:
            with thriftClient(self.port) as client:
                response = client.getAssistentManagerStatus(
                    AssistentManagerStatusRequest(self.tag)
                )
                self.info = response.amInfo
        except Exception as e:
            amLog(f"setup failed: {e}")

        if not self.info:
            # we aren't recognized by the container manager; We are rogue!
            # lets fail fast
            amLog("unmanaged container found! Exiting...")
            sys.exit(1)

    def startContainer(self):
        """
        Prepare the container settings, such as additional cgroup restrictions
        just for the container, filesystem preparations, ulimit adjustments,
        log handling, etc

        Then create the process and move to new cgroup

        NOTE: This is much easier to do with https://lwn.net/Articles/807882/
        which requires clone(2)
        This is a mock assistent and the clone(2) system call is non trivial
        to use in python, so we aren't really making a "container" by some
        defintion of container that usually is definied
        """
        # we're keeping it simple and just starting a subprocess that shares
        # the cgroup with the assistent
        cmdArgs = [self.info.command.cmd] + self.info.command.arguments
        p = subprocess.Popen(cmdArgs)
        self.cpid = p.pid

    def _zombieCheck(self):
        """
        check in a non-blocking way if our container process died
        return exit information if so
        """
        cpid, status = os.waitpid(-1, os.WNOHANG)
        if cpid:
            # non-negative status values means it exited via _exit(2) and returns the int value
            # negative status values mean it was killed by a signal and returns the signal number
            status = os.waitstatus_to_exitcode(status)
            info = ExitInfo()
            info.code = ExitCode.EXIT if status > -1 else ExitCode.SIGNAL
            info.status = abs(status)
            return info
        return None

    def _report(self, info: ExitInfo):
        """
        Report to the container manager the status of the container

        If the agent requests us to abort, we should ungracefully kill the
        workload and exit as soon as possible

        If the agent requests us to stop, we should gracefully kill the container,
        report the results, and exit

        If we can't connect to the container manager, just ignore it

        Exercise:
        1) therer should be a timeout for how long an assistent will wait
        for the manager to come back on line; something long like 12hrs
        to avoid brief manager flakiness
        """
        request = ReportContainerStatusRequest()
        request.tag = self.tag
        request.state = ContainerState.RUNNING if not info else ContainerState.DEAD
        request.pid = os.getpid()
        request.workloadPid = self.cpid
        try:
            with thriftClient(self.port) as client:
                response = client.reportContainerStatus(request)
                if response.status == ManagerResponse.ABORT:
                    amLog(self.tag, "Container manager does not recognize us! Abort!!")
                    # send signal to child process (ungracefully)
                    # and monitor child for it's death
                    os.kill(self.cpid, signal.SIGKILL)
                    # exit uncleanly
                    sys.exit(1)
                elif response.status == ManagerResponse.STOP:
                    # send signal to child process (gracefully)
                    # and monitor child for it's death
                    os.kill(self.cpid, signal.SIGTERM)
        except Exception as e:
            # this can occur if there's an issue connection to container manager
            # e.g container manager is down. We should log and wait for container
            # manager to return
            amLog(self.tag, e)

    def monitor(self):
        while True:
            # check if child died
            cInfo = self._zombieCheck()
            # report to container manager
            self._report(cInfo)

            # exit loop if child is dead
            if cInfo:
                amLog(self.tag, f"Container workload {self.cpid} exited with results: {cInfo}")
                break

            sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "port", type=int, help="port number to use to connect to server"
    )
    parser.add_argument(
        "tag", type=str, help="identifier for container and assistent manager"
    )
    args = parser.parse_args()
    tag = args.tag
    port = args.port
    assistent = Assistent(port, tag)
    # set up container
    assistent.startContainer()
    # monitor the container workload until it's dead
    assistent.monitor()
    amLog(tag, "exiting!")
    sys.exit(0)
