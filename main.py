#!/usr/bin/env python3

import argparse
import os
import signal
import sys

sys.path.append("gen-py")

from functools import partial
from container_manager import ContainerManager
from manager import ContainerManagerHandler
from executor import Executor

from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer


def signalHandler(signum, frame, pid):
    os.kill(pid, signal.SIGKILL)
    # best effort reaping of child process, worst case child will be
    # reparented and reaped by init
    os.waitpid(pid, 0)
    print(f"Received signal {signum}! Exiting!")
    sys.exit(0)


def registerSignalHandler(pid):
    global signalHandler
    signalHandler = partial(signalHandler, pid=pid)
    signal.signal(signal.SIGTERM, signalHandler)
    signal.signal(signal.SIGINT, signalHandler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p", "--port", type=int, help="port number to use for server", default=9090
    )
    parser.add_argument(
        "--no-executor",
        help=" do not spawn an executor process to help drive state machine",
        action="store_true",
    )
    parser.add_argument(
        "--parent-cgroup",
        type=str,
        help="cgroup to start containers",
        default="/sys/fs/cgroup/containers.slice",
    )
    parser.add_argument(
        "--assistent-manager-bin",
        type=str,
        help="path to the assistent manager binary",
        default="./assistent_manager.py",
    )
    args = parser.parse_args()

    if not args.no_executor:
        print("CManager: Spawning Executor process")
        pid = os.fork()
        if pid == 0:
            # child should invoke executor funtion (and not return)
            Executor(args.port, args.parent_cgroup, args.assistent_manager_bin).driveState()
            # if we reached here something bad happened
            sys.exit(1)
        else:
            # set up signal handler to kill executor along side the main process
            registerSignalHandler(pid)

    # set up thrift server
    handler = ContainerManagerHandler()
    processor = ContainerManager.Processor(handler)
    transport = TSocket.TServerSocket(host="127.0.0.1", port=args.port)
    tfactory = TTransport.TBufferedTransportFactory()
    pfactory = TBinaryProtocol.TBinaryProtocolFactory()

    server = TServer.TSimpleServer(processor, transport, tfactory, pfactory)

    print(f"CManager: Container Manager starting on port {args.port}...")
    server.serve()
    print("done.")
