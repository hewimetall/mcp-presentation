# mcp-presentation-docker

PyPI: **`mcp-presentation-docker`** · import: `mcp_docker`

ContainerRuntime port + **bollard** adapter — Docker Engine API, no `docker` CLI.

```bash
(cd packages/mcp-presentation-docker && maturin develop)
```

```python
from mcp_docker import DockerService

docker = DockerService()
result = docker.run(
    "mcp-presentation/web-builder:latest",
    ["web"],
    binds=["/host/ws:/work"],
    workdir="/work",
)
print(result["status_code"], result["logs"])
```
