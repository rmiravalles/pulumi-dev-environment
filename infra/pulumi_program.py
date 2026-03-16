import pulumi
import pulumi_azure_native as azure
from pulumi import Config

config = Config()
pr = config.require("pr")
image = config.get("image") or "nginx"
env_type = config.get("env_type") or "standard"

RESOURCE_PROFILES = {
    "standard": {"cpu": 0.25, "memory": "0.5Gi"},
    "large":    {"cpu": 0.5,  "memory": "1.0Gi"},
}
resources = RESOURCE_PROFILES.get(env_type, RESOURCE_PROFILES["standard"])

location = "westeurope"

rg = azure.resources.ResourceGroup(
    f"rg-pr-{pr}",
    location=location
)

env = azure.app.ManagedEnvironment(
    f"env-pr-{pr}",
    resource_group_name=rg.name,
    location=location
)

app = azure.app.ContainerApp(
    f"app-pr-{pr}",
    resource_group_name=rg.name,
    managed_environment_id=env.id,
    configuration={
        "ingress": {
            "external": True,
            "target_port": 80
        }
    },
    template={
        "containers": [{
            "name": "demo",
            "image": image,
            "resources": {
                "cpu": resources["cpu"],
                "memory": resources["memory"]
            }
        }]
    }
)

pulumi.export("url", app.configuration.apply(
    lambda c: f"https://{c['ingress']['fqdn']}" if c else None
))