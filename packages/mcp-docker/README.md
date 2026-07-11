# mcp-docker

**ContainerRuntime** port + **BollardDockerAdapter** (Docker Engine API, без `docker` CLI).

```python
from mcp_docker import DockerService

docker = DockerService()
result = docker.run(
    image="ghcr.io/example/pdf-builder:latest",
    cmd=["build"],
    binds=["/abs/workspaces/ws1:/work"],
    workdir="/work",
)
print(result["status_code"], result["logs"])
```

ADR-0012 · DooD socket (ADR-0008).
