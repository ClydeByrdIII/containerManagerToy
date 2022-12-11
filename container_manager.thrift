/**
 * Thrift files can namespace, package, or prefix their output in various
 * target languages.
 */
 
namespace cpp container_manager
 
/**
 * In Linux when a process exits, the parent must call wait on the zombie (child) process
 * the wait() family of system calls are used to receive the exit information about the child
 * the exit code is set to (basically) CLD_EXITED (child called _exit(2)) or CLD_KILLED 
 * (child killed by a signal)
 * 
 * In order to interpret the exit code, exit status can be used to obtain the argument passed to
 * _exit(2) argument or the number of the signal that caused the child to terminate
 * see https://man7.org/linux/man-pages/man2/wait.2.html for details
 */
enum ExitCode {
    EXIT = 1,
    SIGNAL = 2
}

struct ExitInfo {
    1: ExitCode code
    2: i32 status
}

/**
 * READY: A container can be "ready" to be run (aka runnable) meaning the container manager
 * has prepared everything for the container to be invoked
 * 
 * RUNNING: A container is currently running
 * 
 * DEAD: A container has exited or was killed by a signal
 * 
 * LOST: A container's status is unknown
 */
enum ContainerState {
    READY = 1,
    RUNNING = 2,
    STOPPING = 3,
    DEAD = 4,
    LOST = 5,
}

struct ContainerInfo {
    1: string tag           // the container identifier
    2: ContainerState state
    3: ExitInfo exitInfo
}

/**
 * the input of exec(2) family of functions typically include a cmd and args.
 * Excercise: include a list of linux capabilities the command should have in
 * order to run (and perhaps drop all other unneeded ones)
 */
struct Command {
    1: string cmd
    2: list<string> arguments
}

struct AssistentManagerInfo {
    1: string tag // the identifier of the container to manage
    2: Command command // command the assistent  should execute
    3: i32 pid // max pid value is 2^22 (see man 5 proc) which fits in 32 bits
    4: i32 workloadPid // pid of the container workload (aka command's pid)
}

/**
 * As similar as these request structs seem, in practice each of these requests
 * can be customized with various options to determine how the container manager
 * should proceed. As this is purely for educational purposes and meant to be extended
 * I shall keep them separated
 */

struct CreateContainerRequest {
    1: string tag
}

struct StartContainerRequest {
    1: string tag
    2: Command command
}

struct StopContainerRequest {
    1: string tag
}

struct DeleteContainerRequest {
    1: string tag
}

struct ListContainerRequest {
    1: list<string> tags
}

struct ListContainerResponse {
    1: list<ContainerInfo> containerInfos
}

struct ContainerIdResponse {
    1: list<string> tags
}

/**
 * The container manager will respond to the assistent manager with
 * OKAY if there's nothing to do
 * STOP if the container should be stopping
 * ABORT if the container should ungracefully be killed
 */

enum ManagerResponse {
    OKAY = 1,
    STOP = 2,
    ABORT = 3,
}

struct ReportContainerStatusRequest {
    1: string tag
    2: ContainerState state
    3: i32 pid
    4: i32 workloadPid
    5: ExitInfo exitInfo
}

struct ReportContainerStatusResponse {
    1: ManagerResponse status
}

struct AssistentManagerStatusRequest {
    1: string tag
}

struct AssistentManagerStatusResponse {
    1: AssistentManagerInfo amInfo
}

exception InvalidOperation {
    1: string what
}

/**
 * Thrift Service defining all container management APIs a caller would use 
 * for container management
 */
service ContainerManager {
    /* API for a human / scheduler to use */

    // Create a container instance in the READY state
    void createContainer(1: CreateContainerRequest request) throws (1:InvalidOperation error),

    // Start a container instance and bring it to the RUNNING state
    void startContainer(1: StartContainerRequest request) throws (1:InvalidOperation error),

    // Stop a container instance and bring it to the DEAD state
    void stopContainer(1: StopContainerRequest request) throws (1:InvalidOperation error),

    // Delete a container instance
    void deleteContainer(1: DeleteContainerRequest request) throws (1:InvalidOperation error),

    // List all known container instances (in any state)
    ListContainerResponse listContainers(1: ListContainerRequest request) throws (1:InvalidOperation error),

    /* API for the executor to use */
    
    // Empty the queue of ready containers (for transitioning to running)
    ContainerIdResponse dequeueReadyContainers(),

    // Get all running containers
    ContainerIdResponse getRunningContainers(),

    /* API for the assistent container manager to use */
 
    // Get information about a certain manager
    AssistentManagerStatusResponse getAssistentManagerStatus(1: AssistentManagerStatusRequest request),

    // Report the container's status to the container manager
    ReportContainerStatusResponse reportContainerStatus(1: ReportContainerStatusRequest request)
}