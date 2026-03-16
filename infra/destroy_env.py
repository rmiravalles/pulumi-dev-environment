import argparse
import sys
from pathlib import Path

import pulumi.automation as auto


INFRA_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Destroy the Azure preview environment for a pull request."
    )
    parser.add_argument("pr_number", type=int, help="Pull request number")
    return parser.parse_args()


def destroy_stack(pr_number: str) -> None:
    stack_name = f"pr-{pr_number}"
    stack = auto.select_stack(
        stack_name=stack_name,
        work_dir=str(INFRA_DIR),
    )

    print("Destroying environment...")
    stack.destroy(on_output=print)

    print("Removing stack metadata...")
    stack.workspace.remove_stack(stack_name)

    print("Environment removed.")


def main() -> int:
    args = parse_args()

    try:
        destroy_stack(str(args.pr_number))
    except Exception as exc:
        print(f"Failed to destroy preview environment: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())