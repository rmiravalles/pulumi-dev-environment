# pulumi-dev-environment

This repository provisions short-lived Azure preview environments for pull requests by using Pulumi Automation API from Python and GitHub Actions.

For each pull request, the workflow creates a dedicated Azure Container Apps environment and deploys a simple public container app. The workflow then comments the resulting preview URL back onto the pull request. When the pull request is merged, the corresponding infrastructure is destroyed and the Pulumi stack is removed.

## What This Repository Does

The repository implements a per-PR preview environment pattern:

- On pull request open or update, GitHub Actions runs `infra/create_env.py`.
- The script creates or selects a Pulumi stack named `pr-<number>` in a Pulumi project named `preview`.
- The Pulumi program in `infra/pulumi_program.py` creates Azure resources in `westeurope`.
- The deployment exports a public application URL.
- The preview workflow comments that URL on the pull request.
- On pull request close, if the PR was merged, GitHub Actions runs `infra/destroy_env.py`.
- The destroy script tears down the Azure resources and removes the Pulumi stack.

## Architecture

The current Pulumi program creates the following resources for each pull request:

- An Azure Resource Group named `rg-pr-<pr-number>`
- An Azure Container Apps managed environment named `env-pr-<pr-number>`
- An Azure Container App named `app-pr-<pr-number>`

The container app currently runs the public `nginx` image with:

- External ingress enabled
- Target port `80`
- `0.25` vCPU
- `0.5Gi` memory

The stack exports a single output named `url`, intended to be the public HTTPS endpoint for the deployed container app.

## Repository Layout

```text
.
├── .github/workflows/
│   ├── destroy.yaml
│   └── preview.yaml
├── infra/
│   ├── __main__.py
│   ├── create_env.py
│   ├── destroy_env.py
│   ├── Pulumi.yaml
│   └── pulumi_program.py
├── Dockerfile
├── requirements.txt
└── README.md
```

## How It Works

### 1. Preview deployment workflow

`.github/workflows/preview.yaml` is triggered on pull request events:

- `opened`
- `synchronize`

That workflow:

1. Checks out the repository
2. Sets up Python 3.12
3. Installs Python dependencies from `requirements.txt`
4. Installs the Pulumi CLI
5. Authenticates to Azure using `azure/login`
6. Logs in to ACR and builds a container image from the branch code, tagged `pr-<number>-<short-sha>`
7. Runs `python infra/create_env.py <pr-number> --image <image-ref>`
8. Posts or updates a comment on the pull request with the preview URL

### 2. Stack creation script

`infra/create_env.py` uses `pulumi.automation` to:

1. Create or select a stack named `pr-<pr-number>`
2. Install the `azure-native` Pulumi plugin at version `v2.0.0`
3. Set the Pulumi config keys `pr` and `image`
4. Run `pulumi up`
5. Print the exported preview URL
6. Expose that URL as a GitHub Actions step output when running in CI

### 3. Pulumi program

`infra/Pulumi.yaml` defines the Pulumi project, and `infra/__main__.py` loads `infra/pulumi_program.py` as the program entrypoint. The Pulumi program reads the `pr` config value, generates resource names, provisions the Azure resources, and exports a URL for the deployed container app.

### 4. Destroy workflow

`.github/workflows/destroy.yaml` is triggered when a pull request is closed. It only runs the destroy job when the PR was merged:

```yaml
if: github.event.pull_request.merged == true
```

That workflow:

1. Checks out the repository
2. Sets up Python 3.12
3. Installs Python dependencies
4. Installs the Pulumi CLI
5. Logs in to Azure
6. Runs `python infra/destroy_env.py <pr-number>`

### 5. Stack destruction script

`infra/destroy_env.py`:

1. Selects the existing stack named `pr-<pr-number>`
2. Runs `pulumi destroy`
3. Removes the stack from the Pulumi backend

## Prerequisites

To use this repository locally or in CI, the following are required:

- Python 3.12 or compatible
- Pulumi CLI installed and available on `PATH`
- Azure credentials with permission to create and destroy:
  - Resource groups
  - Container Apps environments
  - Container Apps
- Python packages listed in `requirements.txt`

This repository is configured to use an Azure Blob Storage Pulumi backend.

You need backend access configured via:

- `PULUMI_BACKEND_URL` (for example: `azblob://pulumi-state`)
- `AZURE_STORAGE_ACCOUNT`
- `AZURE_STORAGE_KEY`

## Installation

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install and authenticate required CLIs:

```bash
pulumi login <your-azblob-backend-url>
az login
```

## Running Locally

Create a preview environment for PR `123`:

```bash
python infra/create_env.py 123
```

Destroy the preview environment for PR `123`:

```bash
python infra/destroy_env.py 123
```

## GitHub Actions Configuration

The workflows expect GitHub repository configuration for Azure authentication.

### Required secret

- `AZURE_CREDENTIALS`

This secret is passed to `azure/login@v2` and should contain service principal credentials in JSON format.

For the Azure Blob backend used by this repository, configure these additional GitHub secrets:

- `PULUMI_BACKEND_URL` (for example: `azblob://pulumi-state`)
- `AZURE_STORAGE_ACCOUNT`
- `AZURE_STORAGE_KEY`
- `AZURE_CONTAINER_REGISTRY` — the ACR name (without `.azurecr.io`), used to build and push the container image

The workflows run `pulumi login` against `PULUMI_BACKEND_URL` before create and destroy operations.

## Configuration Model

The Pulumi program currently uses one config value:

- `pr`: the pull request number

That value is set automatically by `infra/create_env.py` and consumed by `infra/pulumi_program.py` to derive resource names.

The Azure region is currently hard-coded to:

- `westeurope`

## Current Behavior and Assumptions

This repository is intentionally minimal. At the moment it assumes:

- Preview environments are keyed only by PR number
- Each PR gets its own Pulumi stack
- The deployed workload is a demo `nginx` container rather than an application image built from this repository
- The same Azure subscription and credentials are used for create and destroy operations
- The preview workflow updates a single PR comment instead of creating a new one on every deployment

## Known Gaps

The current implementation is enough to express the preview-environment pattern, but there are operational gaps you should be aware of:

- There is no validation, retry handling, or cleanup logic for partial failures.
- There are no tests, linting, or formatting checks.

## Extending This Repository

Typical next improvements would be:

- Replace the demo `nginx` container with an application image built in CI
- Make region, image, CPU, memory, and environment variables configurable
- Add stronger deployment error handling and cleanup for partial failures
- Add protection against orphaned stacks when a workflow fails midway

## Dependencies

Python dependencies are currently:

- `pulumi`
- `pulumi-azure-native`

## Summary

This repository is a small Pulumi Automation API prototype for pull-request-based Azure preview environments. It uses GitHub Actions to create an isolated Azure Container App per PR and remove it again after merge.