#!/usr/bin/env python3
"""
Blacky – your terminal sidekick for interacting with Azure DevOps

Usage:
  blacky create-pr [--dry-run] -- <extra az repos pr create args>

Example:
  blacky create-pr --dry-run -- --draft
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List

# ---------------------------------------------------------------------------
# Constants / Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_FILE = "blacky.conf.json"

# ---------------------------------------------------------------------------
# Pretty logging / messages
# ---------------------------------------------------------------------------

def _prefix() -> str:
    return "🦜"

def info(msg: str) -> None:
    print(f"{_prefix()} {msg}")

def warn(msg: str) -> None:
    print(f"{_prefix()}:warn  {msg}", file=sys.stderr)

def error(msg: str) -> None:
    print(f"{_prefix()}:error {msg}", file=sys.stderr)

def print_section(title: str) -> None:
    """Visual section separator for longer flows."""
    line = "-" * max(10, len(title) + 4)
    print(f"\n{line}\n{title}\n{line}")

# ---------------------------------------------------------------------------
# Config handling (JSON)
# ---------------------------------------------------------------------------

@dataclass
class AzureConfig:
    organization_url: str
    project: str
    repository: str

@dataclass
class BlackyConfig:
    pr_title_regex: str
    package_manager: str
    target_branch: str
    project_pkg_prefix: str
    azure: AzureConfig

def load_config_file(config_path: Path) -> Optional[BlackyConfig]:
    """
    Load configuration from blacky.conf.json.

    Expected shape:
    {
      "prTitleRegex": "...",
      "packageManager": "pnpm",
      "azure": {
        "organizationUrl": "https://dev.azure.com/<org>",
        "project": "<project>",
        "repository": "<repo-name>"
      }
    }
    """
    if not config_path.exists():
        warn(
            f"Configuration file not found at: {config_path}\n"
            "Blacky expects a blacky.conf.json in your project root."
        )
        return None

    try:
        with config_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        error(
            f"Could not parse {config_path} as JSON: {e}\n"
            "Please fix the JSON syntax (trailing commas, quotes, etc.)."
        )
        return None

    def missing(path: str) -> None:
        error(f"Missing required config key: {path}")

    pr_title_regex = raw.get("prTitleRegex")
    package_manager = raw.get("packageManager")
    target_branch = raw.get("targetBranch")
    project_pkg_prefix = raw.get("projectPackagePrefix")
    azure_raw = raw.get("azure") or {}

    org_url = azure_raw.get("organizationUrl")
    project = azure_raw.get("project")
    repo = azure_raw.get("repository")

    missing_keys: List[str] = []
    if not pr_title_regex:
        missing_keys.append("prTitleRegex")
    if not target_branch:
        missing_keys.append("targetBranch")
    if not project_pkg_prefix:
        missing_keys.append("projectPackagePrefix")
    if not package_manager:
        missing_keys.append("packageManager")
    if not org_url:
        missing_keys.append("azure.organizationUrl")
    if not project:
        missing_keys.append("azure.project")
    if not repo:
        missing_keys.append("azure.repository")

    if missing_keys:
        error("Your blacky.conf.json is missing some required fields:")
        for key in missing_keys:
            print(f"  - {key}", file=sys.stderr)

        print(
            "\nExample configuration:\n"
            "{\n"
            '  "prTitleRegex": "^feature/(?P<title>.+)$",\n'
            '  "packageManager": "pnpm",\n'
            '  "targetBranch": "main",\n'
            '  "azure": {\n'
            '    "organizationUrl": "https://dev.azure.com/<org>",\n'
            '    "project": "<project>",\n'
            '    "repository": "<repo-name>"\n'
            "  }\n"
            "}\n",
            file=sys.stderr,
        )
        return None

    azure = AzureConfig(
        organization_url=org_url,
        project=project,
        repository=repo,
    )
    return BlackyConfig(
        pr_title_regex=pr_title_regex,
        package_manager=package_manager,
        azure=azure,
        target_branch=target_branch,
        project_pkg_prefix=project_pkg_prefix
    )

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
    """
    try:
        pattern = re.compile(regex_pattern)
    except re.error as e:
        warn(
            f"Configured prTitleRegex is invalid ({e}). "
            "Falling back to using the branch name as the PR title."
        )
        return branch

    m = pattern.search(branch)
    if not m:
        warn(
            "Configured prTitleRegex did not match the branch name. "
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
    print_section("PR Description")
    info(prompt)
    print("Finish input with a single line '.' or EOF (Ctrl+D):")
    lines: List[str] = []
    while True:
        try:
            line = input("> ")
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
    print_section("Change Type")
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
    info(f"Running command:\n  {' '.join(cmd)}")
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

    return sorted([pkg for pkg in packages if len(pkg) > 1])

# ---------------------------------------------------------------------------
# Helper: create / edit changeset
# ---------------------------------------------------------------------------

def create_and_edit_changeset(
    package_manager: str,
    description_md: str,
    change_type: str,
    cwd: Path,
    project_pkg_prefix: str,
) -> Optional[Path]:
    """
    - Run `<package-manager> changeset --empty`
    - Find latest changeset file
    - Fill in affected packages and change type
    - Append / include description
    """
    print_section("Changeset")
    try:
        run_command([package_manager, "changeset", "--empty"], cwd=cwd)
    except subprocess.CalledProcessError:
        error(
            f"{package_manager} changeset --empty failed. "
            "Is the changeset CLI installed and available in PATH?"
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

    front_matter_lines = ["---"]
    for pkg_path in changed_packages:
        # Use folder name as package name heuristic
        pkg_name = Path(pkg_path).name
        front_matter_lines.append(f'"{project_pkg_prefix}/{pkg_name}": {change_type}')
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
    """
    print_section("Local Build")
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
        run_command([package_manager, "run", "build:all"], cwd=cwd)
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
    print_section("Azure DevOps PR")
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
        print("  " + " ".join(f"'{c}'" if ' ' in c else c for c in cmd))
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

    print_section("Configuration")
    config = load_config_file(cwd / DEFAULT_CONFIG_FILE)
    if not config:
        return 1

    # Git branch
    print_section("Git")
    current_branch = get_current_branch()
    if not current_branch:
        error("Without a current branch I cannot create a PR.")
        return 1

    # Determine PR title
    title = build_pr_title_from_branch(current_branch, config.pr_title_regex)
    info(f"Suggested PR title: {title}")

    # Ask description
    description = ask_multiline_markdown(
        "Please provide a PR description in Markdown."
    )
    if not description:
        warn("You did not provide a description. The PR will be a bit terse.")

    # Ask change type
    change_type = ask_change_type()

    # Create & edit changeset
    changeset_path = create_and_edit_changeset(
        package_manager=config.package_manager,
        description_md=description,
        change_type=change_type,
        cwd=cwd,
        project_pkg_prefix=config.project_pkg_prefix
    )
    if not changeset_path:
        error(
            "I could not create a valid changeset. "
            "No PR without a changeset, sorry."
        )
        return 1

    # Run local build
    if not run_local_build(package_manager=config.package_manager, cwd=cwd):
        return 1

    # Prepare extra args for 'az' from the CLI after '--'
    extra_az_args = args.az_args if args.az_args else []

    # Create PR via Azure CLI
    success = create_azure_pr(
        org_url=config.azure.organization_url,
        project=config.azure.project,
        repo=config.azure.repository,
        source_branch=current_branch,
        target_branch=config.target_branch,
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
    description = (
        "blacky – your little helper for pull requests with Azure DevOps & changesets.\n\n"
        "Typical workflow:\n"
        "  1. Read configuration from blacky.conf.json in the project root.\n"
        "  2. Read git information (current branch, etc.).\n"
        "  3. Build a PR title based on the branch name via prTitleRegex.\n"
        "  4. Ask for PR description (Markdown).\n"
        "  5. Ask for change type (patch/minor/major).\n"
        "  6. Run '<packageManager> changeset --empty' and update the changeset file.\n"
        "  7. Run '<packageManager> install' and '<packageManager> run build'.\n"
        "  8. Create the PR via 'az repos pr create' (or simulate with --dry-run).\n\n"
        "Examples:\n"
        "  blacky create-pr --dry-run\n"
        "  blacky create-pr -- --draft --auto-complete\n\n"
        "Config file example (blacky.conf.json):\n"
        '{\n'
        '  "prTitleRegex": "^feature/(?P<title>.+)$",\n'
        '  "packageManager": "pnpm",\n'
        '  "azure": {\n'
        '    "organizationUrl": "https://dev.azure.com/<org>",\n'
        '    "project": "<project>",\n'
        '    "repository": "<repo-name>"\n'
        "  }\n"
        "}\n"
    )

    parser = argparse.ArgumentParser(
        prog="blacky",
        description=description,
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
            "Everything after '--' is passed directly to 'az repos pr create',\n"
            "without using the shell (arguments are passed as a list).\n\n"
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
            "Example: blacky create-pr -- --draft --auto-complete"
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
