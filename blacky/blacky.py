#!/usr/bin/env python3
"""
Blacky – your terminal sidekick for interacting with Azure DevOps

Usage:
  blacky create-pr [--dry-run] -- <extra az repos pr create args>

Example:
  blacky create-pr --dry-run -- --draft
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, List

# ---------------------------------------------------------------------------
# Constants / Defaults
# ---------------------------------------------------------------------------

DEFAULT_ENV_FILE = ".env"

# Expected env keys (can be extended)
ENV_KEY_PR_TITLE_REGEX = "BLACKY_PR_TITLE_REGEX"
ENV_KEY_PACKAGE_MANAGER = "BLACKY_PACKAGE_MANAGER"
ENV_KEY_AZURE_ORG = "BLACKY_AZURE_ORG_URL"
ENV_KEY_AZURE_PROJECT = "BLACKY_AZURE_PROJECT"
ENV_KEY_AZURE_REPO = "BLACKY_AZURE_REPO"


# ---------------------------------------------------------------------------
# Helper: Logging / errors
# ---------------------------------------------------------------------------

def info(msg: str) -> None:
    print(f"[blacky] {msg}")


def warn(msg: str) -> None:
    print(f"[blacky:warn] {msg}", file=sys.stderr)


def error(msg: str) -> None:
    print(f"[blacky:error] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Helper: .env parsing (no external deps, simple parser)
# ---------------------------------------------------------------------------

def load_env_file(env_path: Path) -> Dict[str, str]:
    """
    Minimal .env loader that:
    - Ignores empty lines and comments (#)
    - Supports KEY=VALUE and KEY="VALUE" / KEY='VALUE'
    - Does not do variable interpolation
    """
    env: Dict[str, str] = {}

    if not env_path.exists():
        warn(
            f"No .env file found at: {env_path}. "
            f"Blacky is a bit blind without project context."
        )
        return env

    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()

            # Strip matching quotes
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]

            env[key] = value

    return env


# ---------------------------------------------------------------------------
# Helper: git info
# ---------------------------------------------------------------------------

def get_current_branch() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        if branch == "HEAD":
            return None
        return branch
    except subprocess.CalledProcessError:
        error("Could not determine current git branch. Are you inside a git repository?")
        return None


def get_git_remote_url() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        warn("Could not determine remote URL for 'origin'. Proceeding without it.")
        return None


# ---------------------------------------------------------------------------
# Helper: PR title from branch
# ---------------------------------------------------------------------------

def build_pr_title_from_branch(branch: str, regex_pattern: str) -> str:
    """
    Build a PR title from a branch name using a configurable regex pattern.
    The regex is expected to contain named or unnamed groups; we will use:
    - The first named group 'title' if present.
    - Otherwise: the first capturing group.
    - If no groups match: fall back to branch name.
    """
    try:
        pattern = re.compile(regex_pattern)
    except re.error as e:
        warn(
            f"BLACKY_PR_TITLE_REGEX is invalid ({e}). "
            f"Falling back to using the branch name as the PR title."
        )
        return branch

    m = pattern.search(branch)
    if not m:
        warn(
            "Configured regex did not match the branch name. "
            "Falling back to using the branch name as PR title."
        )
        return branch

    if "title" in m.groupdict() and m.group("title"):
        return m.group("title").strip()

    if m.groups():
        return m.group(1).strip()

    return branch


# ---------------------------------------------------------------------------
# Helper: ask user for input (description, change type)
# ---------------------------------------------------------------------------

def ask_multiline_markdown(prompt: str) -> str:
    info(prompt)
    print("(Finish input with a single line '.' or EOF (Ctrl+D))")
    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == ".":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def ask_change_type() -> str:
    """
    Ask user for change type: patch / minor / major.
    """
    valid = {"patch", "minor", "major"}
    while True:
        answer = input("Change type for this changeset? [patch/minor/major]: ").strip().lower()
        if answer in valid:
            return answer
        print("Please enter 'patch', 'minor' or 'major'.")


# ---------------------------------------------------------------------------
# Helper: run commands (safe-ish)
# ---------------------------------------------------------------------------

def run_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    info(f"Running command: {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=False,
        check=check,
    )


# ---------------------------------------------------------------------------
# Helper: find latest changeset file created
# ---------------------------------------------------------------------------

def find_latest_changeset_file(changesets_dir: Path) -> Optional[Path]:
    if not changesets_dir.exists():
        return None

    candidates = sorted(
        [p for p in changesets_dir.glob("*.md") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0]


# ---------------------------------------------------------------------------
# Helper: read changed packages (simple heuristic)
# ---------------------------------------------------------------------------

def get_changed_packages() -> List[str]:
    """
    Very simple heuristic: find changed package directories with package.json.
    Assumes workspaces with subfolders that contain package.json.

    This is intentionally simple and may need to be adapted for a real monorepo.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        warn("Could not execute 'git status'. Assuming no changed packages.")
        return []

    changed_files = [line[3:] for line in result.stdout.splitlines() if line.strip()]
    packages: set[str] = set()

    for file in changed_files:
        p = Path(file)
        # Look upwards until we find a package.json
        for parent in [p] + list(p.parents):
            pkg_json = parent / "package.json"
            if pkg_json.exists():
                packages.add(parent.as_posix())
                break

    return sorted(packages)


# ---------------------------------------------------------------------------
# Helper: create / edit changeset
# ---------------------------------------------------------------------------

def create_and_edit_changeset(
    package_manager: str,
    description_md: str,
    change_type: str,
    cwd: Path,
) -> Optional[Path]:
    """
    - Run `<package-manager> changeset --empty`
    - Find latest changeset file
    - Fill in affected packages and change type
    - Append / include description
    """
    try:
        run_command([package_manager, "changeset", "--empty"], cwd=cwd)
    except subprocess.CalledProcessError:
        error(
            f"{package_manager} changeset --empty failed. "
            f"Is the changeset CLI installed and available in PATH?"
        )
        return None

    changesets_dir = cwd / ".changeset"
    latest = find_latest_changeset_file(changesets_dir)
    if not latest:
        error(
            "I could not find a newly created changeset file in .changeset. "
            "Did the command actually create one?"
        )
        return None

    info(f"Editing changeset file: {latest}")

    changed_packages = get_changed_packages()
    if not changed_packages:
        warn(
            "I could not find any changed packages with a package.json. "
            "The changeset will be created without explicit package entries."
        )

    # Changeset format (simplified):
    #
    # ---
    # "package-1": patch
    # "package-2": minor
    # ---
    #
    # Description...
    #
    front_matter_lines = ["---"]
    for pkg_path in changed_packages:
        # Use folder name as package name heuristic
        pkg_name = Path(pkg_path).name
        front_matter_lines.append(f'"{pkg_name}": {change_type}')
    front_matter_lines.append("---")
    front_matter_lines.append("")  # empty line

    with latest.open("w", encoding="utf-8") as f:
        f.write("\n".join(front_matter_lines))
        if description_md:
            f.write(description_md.strip())
            f.write("\n")

    info("Changeset has been updated.")
    return latest


# ---------------------------------------------------------------------------
# Helper: run local builds (very simple / configurable via env?)
# ---------------------------------------------------------------------------

def run_local_build(package_manager: str, cwd: Path) -> bool:
    """
    Run a basic install + build using the package manager.
    This is intentionally simple. Adjust if you need something more advanced.
    """
    # install
    try:
        run_command([package_manager, "install"], cwd=cwd)
    except subprocess.CalledProcessError:
        error(
            "Installation step (install) failed. "
            "Blacky will abort before creating a PR."
        )
        return False

    # build – many repos use 'build'
    try:
        run_command([package_manager, "run", "build"], cwd=cwd)
    except subprocess.CalledProcessError:
        error(
            "Build step failed. "
            "I will not create a PR while the project does not build locally."
        )
        return False

    info("Local build completed successfully.")
    return True


# ---------------------------------------------------------------------------
# Helper: azure devops CLI PR creation
# ---------------------------------------------------------------------------

def create_azure_pr(
    org_url: str,
    project: str,
    repo: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description_md: str,
    extra_az_args: List[str],
    cwd: Path,
    dry_run: bool,
) -> bool:
    """
    Create a PR using Azure CLI:
    az repos pr create --title ... --description ... --source-branch ... --target-branch ...
    """
    base_cmd = [
        "az",
        "repos",
        "pr",
        "create",
        "--organization",
        org_url,
        "--project",
        project,
        "--repository",
        repo,
        "--source-branch",
        source_branch,
        "--target-branch",
        target_branch,
        "--title",
        title,
        "--description",
        description_md,
    ]

    cmd = base_cmd + extra_az_args

    if dry_run:
        info("Dry-run is enabled: I will show you what I would do, but no PR will be created.")
        print("Command would be:")
        print(" ".join(f"'{c}'" if ' ' in c else c for c in cmd))
        return True

    try:
        run_command(cmd, cwd=cwd)
        info("Pull request was created successfully via Azure CLI.")
        return True
    except subprocess.CalledProcessError:
        error("Creating the PR with Azure CLI failed.")
        return False


# ---------------------------------------------------------------------------
# create-pr subcommand
# ---------------------------------------------------------------------------

def handle_create_pr(args: argparse.Namespace) -> int:
    cwd = Path(os.getcwd())

    # Load env
    env = load_env_file(cwd / DEFAULT_ENV_FILE)

    # Required envs
    pr_title_regex = env.get(ENV_KEY_PR_TITLE_REGEX)
    package_manager = env.get(ENV_KEY_PACKAGE_MANAGER)
    org_url = env.get(ENV_KEY_AZURE_ORG)
    project = env.get(ENV_KEY_AZURE_PROJECT)
    repo = env.get(ENV_KEY_AZURE_REPO)

    # Validate required envs, but keep error messages "blacky-like"
    missing_envs = []
    if not pr_title_regex:
        missing_envs.append(ENV_KEY_PR_TITLE_REGEX)
    if not package_manager:
        missing_envs.append(ENV_KEY_PACKAGE_MANAGER)
    if not org_url:
        missing_envs.append(ENV_KEY_AZURE_ORG)
    if not project:
        missing_envs.append(ENV_KEY_AZURE_PROJECT)
    if not repo:
        missing_envs.append(ENV_KEY_AZURE_REPO)

    if missing_envs:
        error(
            "I am missing some important hints from your .env file:\n  - "
            + "\n  - ".join(missing_envs)
        )
        print(
            "\nPlease update the .env file in your project root, for example:\n"
            f'{ENV_KEY_PR_TITLE_REGEX}="^feature/(?P<title>.+)$"\n'
            f"{ENV_KEY_PACKAGE_MANAGER}=pnpm\n"
            f"{ENV_KEY_AZURE_ORG}=https://dev.azure.com/<org>\n"
            f"{ENV_KEY_AZURE_PROJECT}=<project>\n"
            f"{ENV_KEY_AZURE_REPO}=<repo-name>\n"
        )
        return 1

    # Git branch
    current_branch = get_current_branch()
    if not current_branch:
        error("Without a current branch I cannot create a PR.")
        return 1

    # Determine PR title
    title = build_pr_title_from_branch(current_branch, pr_title_regex)
    info(f"Suggested PR title: {title}")

    # Ask for target branch (simple, default: main)
    default_target = "main"
    target = input(f"Target branch for the PR? [Default: {default_target}]: ").strip()
    if not target:
        target = default_target

    # Ask description
    description = ask_multiline_markdown(
        "Please provide a PR description in Markdown:"
    )
    if not description:
        warn("You did not provide a description. The PR will be a bit terse.")

    # Ask change type
    change_type = ask_change_type()

    # Create & edit changeset
    changeset_path = create_and_edit_changeset(
        package_manager=package_manager,
        description_md=description,
        change_type=change_type,
        cwd=cwd,
    )
    if not changeset_path:
        error(
            "I could not create a valid changeset. "
            "No PR without a changeset, sorry."
        )
        return 1

    # Run local build
    if not run_local_build(package_manager=package_manager, cwd=cwd):
        return 1

    # Prepare extra args for 'az' from the CLI after '--'
    extra_az_args = args.az_args if args.az_args else []

    # Security note:
    # We forward only extra args after '--' explicitly and do not interpolate them in a shell.
    # Everything is passed as a list to subprocess.run.

    # Create PR via Azure CLI
    success = create_azure_pr(
        org_url=org_url,
        project=project,
        repo=repo,
        source_branch=current_branch,
        target_branch=target,
        title=title,
        description_md=description
        or f"Automatically created by blacky for branch {current_branch}",
        extra_az_args=extra_az_args,
        cwd=cwd,
        dry_run=args.dry_run,
    )

    return 0 if success else 1


# ---------------------------------------------------------------------------
# CLI setup
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blacky",
        description=(
            "blacky – your little helper for pull requests with Azure DevOps & changesets.\n\n"
            "Example:\n"
            "  blacky create-pr --dry-run -- --auto-complete\n\n"
            "Hint: Everything after '--' is passed directly to 'az repos pr create'."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-pr group
    create_pr_parser = subparsers.add_parser(
        "create-pr",
        help="Create (or simulate) a pull request with a changeset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Create an Azure DevOps pull request from the current branch.\n\n"
            "Workflow:\n"
            "  1. Read .env and git information.\n"
            "  2. Build a PR title based on the branch name.\n"
            "  3. Ask for PR description (Markdown).\n"
            "  4. Ask for change type (patch/minor/major).\n"
            "  5. Run '<package-manager> changeset --empty' and update the changeset file.\n"
            "  6. Run '<package-manager> install' and '<package-manager> run build'.\n"
            "  7. Create the PR via 'az repos pr create' (or simulate with --dry-run).\n\n"
            "Examples:\n"
            "  blacky create-pr --dry-run\n"
            "  blacky create-pr -- --draft\n"
        ),
    )
    create_pr_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would happen; do not create a PR.",
    )
    # Everything after '--' is forwarded to Azure CLI
    create_pr_parser.add_argument(
        "az_args",
        nargs=argparse.REMAINDER,
        help=(
            "Options that are passed directly to 'az repos pr create'. "
            "They are forwarded as a list to subprocess.run (no shell)."
        ),
    )
    create_pr_parser.set_defaults(func=handle_create_pr)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
