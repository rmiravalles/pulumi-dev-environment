import argparse
import os
import sys
from pathlib import Path

import pulumi.automation as auto


INFRA_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update an Azure preview environment for a pull request."
    )
    parser.add_argument("pr_number", type=int, help="Pull request number")
    parser.add_argument("--image", default="nginx", help="Container image reference to deploy")
    parser.add_argument(
        "--env-type",
        default="standard",
        choices=["standard", "large"],
        help="Environment size profile (standard or large)",
    )
    return parser.parse_args()


def write_github_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return

    with open(output_file, "a", encoding="utf-8") as file:
        file.write(f"{name}={value}\n")


def create_stack(pr_number: str, image: str, env_type: str) -> None:
    stack_name = f"pr-{pr_number}"
    stack = auto.create_or_select_stack(
        stack_name=stack_name,
        work_dir=str(INFRA_DIR),
    )

    print("Installing Azure plugin...")
    stack.workspace.install_plugin("azure-native", "v2.0.0")

    print("Setting config...")
    stack.set_config("pr", auto.ConfigValue(value=pr_number))
    stack.set_config("image", auto.ConfigValue(value=image))
    stack.set_config("env_type", auto.ConfigValue(value=env_type))

    print("Deploying stack...")
    result = stack.up(on_output=print)

    preview_url = result.outputs.get("url")
    if preview_url is None or not preview_url.value:
        raise RuntimeError("Deployment completed but no preview URL was exported.")

    print("\nPreview URL:")
    print(preview_url.value)
    write_github_output("preview_url", str(preview_url.value))


def main() -> int:
    args = parse_args()

    try:
        create_stack(str(args.pr_number), args.image, args.env_type)
    except Exception as exc:
        print(f"Failed to create preview environment: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())