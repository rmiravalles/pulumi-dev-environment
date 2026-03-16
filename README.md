# pulumi-dev-environment

This repository provisions short-lived Azure preview environments for pull requests by using Pulumi Automation API from Python and GitHub Actions.

For each pull request, the workflow creates a dedicated Azure Container Apps environment and deploys a simple public container app. The workflow then comments the resulting preview URL back onto the pull request. When the pull request is merged, the corresponding infrastructure is destroyed and the Pulumi stack is removed.

## Developer Guide: Creating a Preview Environment

This section is for developers who want to deploy their application into a preview environment by opening a pull request.

### Prerequisites

You need:

- Write access to this repository (or fork it if your organization allows that workflow)
- Docker installed locally if you want to test your image build before pushing
- Your application source code ready to be containerized

### Step 1 — Clone the repository and create a branch

```bash
git clone https://github.com/rmiravalles/pulumi-dev-environment
cd pulumi-dev-environment
git checkout -b my-feature
```

### Step 2 — Add your application code

Put your application source files in the repository root alongside the existing `infra/` folder. For example:

```text
.
├── src/              ← your application code
├── package.json      ← or pyproject.toml, go.mod, etc.
├── Dockerfile        ← your real build definition (see Step 3)
├── infra/
└── ...
```

### Step 3 — Replace the Dockerfile with your real build

Open `Dockerfile` and replace the placeholder content with the build instructions for your application. For example, for a Node.js app:

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
EXPOSE 80
CMD ["node", "dist/index.js"]
```

> **Important:** your application must listen on port `80`. If it listens on a different port, ask a repository maintainer to update `target_port` in `infra/pulumi_program.py`.

You can verify the image builds correctly locally before pushing:

```bash
docker build -t my-app:local .
docker run -p 8080:80 my-app:local
# visit http://localhost:8080
```

### Step 4 — Choose an environment size (optional)

Two resource profiles are available. The default is `standard`. If you need more CPU and memory, you will apply the `env:large` label in Step 6.

| Profile | CPU | Memory |
|---|---|---|
| `standard` (default) | 0.25 vCPU | 0.5Gi |
| `large` | 0.5 vCPU | 1.0Gi |

If you want the large profile, also replace `Dockerfile.large` with your build definition (it can be identical to `Dockerfile` or a separately tuned variant).

### Step 5 — Commit and push your branch

```bash
git add .
git commit -m "add my application"
git push origin my-feature
```

### Step 6 — Open a pull request

Go to the repository on GitHub and open a pull request from your branch against `main`.

- If you want the **standard** environment: open the PR as-is, no label needed.
- If you want the **large** environment: apply the label **`env:large`** to the PR. You can do this in the Labels panel on the right side of the PR page before or after opening it.

### Step 7 — Wait for the preview URL

Within a few minutes the workflow will:

1. Build your container image from the branch code
2. Push it to the container registry
3. Deploy it to Azure Container Apps
4. Post a comment on the PR with the URL

The comment looks like:

```
Preview environment is ready: https://app-pr-<number>.<region>.azurecontainerapps.io
```

### Step 8 — Iterate

Every time you push a new commit to the branch the workflow re-runs automatically and updates the same PR comment with the new deployment URL.

If you change your mind about the environment size, apply or remove the `env:large` label — the workflow re-runs on the `labeled` event and redeploys with the new profile without requiring a push.

### Step 9 — Merge and clean up

When your work is ready, merge the PR. The destroy workflow runs automatically and removes all Azure resources and the Pulumi stack. No manual cleanup is needed.

---

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
├── Dockerfile.large
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
6. Detects the `env:large` PR label to determine the environment profile
7. Logs in to ACR and builds the corresponding container image from the branch code, tagged `pr-<number>-<type>-<short-sha>`
8. Runs `python infra/create_env.py <pr-number> --image <image-ref> --env-type <type>`
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

## Environment Types

Two environment profiles are available, selected by applying a label to the pull request before or after opening it.

| Label | Dockerfile | CPU | Memory |
|---|---|---|---|
| *(none)* | `Dockerfile` | 0.25 | 0.5Gi |
| `env:large` | `Dockerfile.large` | 0.5 | 1.0Gi |

If no label is applied the `standard` profile is used. Changing or adding a label on an already-open PR re-triggers the workflow (`labeled` event) and redeploys with the new profile.

To add further profiles, add a new entry to `RESOURCE_PROFILES` in `infra/pulumi_program.py`, add a corresponding `Dockerfile.<type>`, and extend the label detection step in `preview.yaml`.

## Current Behavior and Assumptions

This repository is intentionally minimal. At the moment it assumes:

- Preview environments are keyed only by PR number
- Each PR gets its own Pulumi stack
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