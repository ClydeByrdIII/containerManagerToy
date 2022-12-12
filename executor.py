#!/usr/bin/env python3

import os
import shutil
import signal
import sys

sys.path.append("gen-py")

from time import sleep

from container_manager import ContainerManager
from client_utils import thriftClient, waitForServer
from container_utils import recursivelyDeleteCgroups, generateUnshareCommand


class Executor:
    """
    The container manager server is basically a state machine that is only
    concerned with updating and maintaining states and metadata.

    All requests should be as quick as possible and all other intensive work
    should be offloaded to the executor thread/process to perform.
    Exercises:
    1) Re-write to use clone(2)
    2) If an assistent manager doesn't report back after a certain period
    of time, transition it to LOST state (as the assistent manager can't do it)
    3) If the executor restarts, and a previously existing assistent manager dies,
    its cgroup won't be cleaned up because the executor is no longer the parent
    and will not receive the sigchld. We should periodically clean up empty,
    unmanaged cgroups
    4) OOM kills can be detected by reading the memory.events file in the assistent
    manager's cgroup.
    5) If the server and executor is down and a previously existing assistent manager
    dies, its exit information is lost. If the assistent manager was executed as a
    transient systemd unit, systemd would keep track of exit information until
    something resets the state of the unit (similar to how processes need wait(2)
    for the process to be cleared from the pid table)
    6) We should support preparing a filesystem that can we can use as the base root
    of the container and chroot-pivot-root in to it (unshare supports this)
    """

    def __init__(self, port: int, cgPath: str, amBinPath: str):
        # port to make thrift requests to
        self.port = port
        # path to the assistent container manager binary
        self.amBinPath = amBinPath
        # assistents forked key is pid of assistent, value is tag of assistent
        self.children = {}
        # path of container cgroup slice
        self.cgroupParentPath = cgPath
        # make initial parent dir, we'd like to fail early if there's an issue here
        os.makedirs(self.cgroupParentPath, mode=0o755, exist_ok=True)
        # wait until the server is up and ready before proceeding
        waitForServer(port)

    def _getContainers(self):
        """
        A consequence of a single threaded thrift server is that it can only
        maintain a single client connection at a time requiring this costly
        overhead per thrift call
        """
        with thriftClient(self.port) as client:
            response = client.dequeueReadyContainers()
        return response.tags

    def _execAssistentManager(self, tag: str):
        def waitForParent(readEnd, writeEnd, ctag):
            # close write end of pipe since we don't need it
            os.close(writeEnd)
            # convert the fd to a file object
            readEnd = os.fdopen(readEnd)
            # wait on the parent via a blocking read call
            msg = readEnd.read()
            # close the read end of the pipe
            readEnd.close()

        def prepareChild(cpid, cgPath, ctag):
            """
            Set up cgroups, resource restrictions, etc for the assistent manager
            """
            # parent creates container cgroup "/{cgPath}/{ctag}"
            dirName = os.path.join(cgPath, ctag)
            os.makedirs(dirName, mode=0o755)
            # move child to that cgroup
            filename = os.path.join(dirName, "cgroup.procs")
            with open(filename, "w") as f:
                f.write(str(pid))

        # set up pipes to be used for synchronization between executor and
        # assistent manager
        r, w = os.pipe()
        # fork process
        # under a better implementation we would be using clone(2) to create the process
        # in its destination cgroup
        # but in python it's non trivial to use clone(2) system call, so we use unshare(1)
        pid = os.fork()
        if pid == 0:
            # This is the child process
            waitForParent(r, w, tag)
            # exec assistent manager in a new mount ns
            cmd = generateUnshareCommand(
                [self.amBinPath, str(self.port), tag, self.cgroupParentPath]
            )
            os.execv(cmd[0], cmd)
            # if we reach here something bad happened
            sys.exit(1)
        else:
            # parent closes the read end of the pipe
            os.close(r)
            # should not be possible
            assert pid not in self.children
            # track cpid and its assistent manager tag
            self.children[pid] = tag
            prepareChild(pid, self.cgroupParentPath, tag)
            # parent writes to the pipe
            os.write(w, b"1")
            os.close(w)
            print(f"Executor: Started assistent manager with tag '{tag}'")

    def _handleZombies(self):
        """
        If there is a zombie child, we need to call one of the wait() family
        of system calls to reap the zombie.

        This also provides us the exit information of the assistent manager
        that could be useful for debugging.

        We also take this chance to clean up the empty cgroup(s) it was using.
        see waitpid(2) NOTES for details on zombies
        """
        cpid, status = os.waitpid(-1, os.WNOHANG)
        if cpid:
            # non-negative status values means it exited via _exit(2) and returns the int value
            # negative status values mean it was killed by a signal and returns the signal number
            print(
                f"Executor: Assistent Manager Process {cpid} associated with "
                f"tag '{self.children[cpid]}' died with status "
                f"{os.waitstatus_to_exitcode(status)}"
            )
            # recursively clean up cgroup "/{cgPath}/{ctag}"
            dirName = os.path.join(self.cgroupParentPath, self.children[cpid])
            recursivelyDeleteCgroups(dirName)
            del self.children[cpid]

    def driveState(self):
        """
        Check if any containers are ready to be executed
        Clean up any already exited containers
        Perform any other cleanup / responsibilities our server can't do
        """
        while True:
            # check for runnable containers to start
            tags = self._getContainers()
            # for each container, fork and exec an Assistent Manager
            for tag in tags:
                self._execAssistentManager(tag)

            # check if any assistent managers died
            if self.children:
                self._handleZombies()

            # sleep for 1 second
            sleep(1)
