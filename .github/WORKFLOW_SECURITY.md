# Workflow security settings

The workflow files enforce least-privilege tokens and protected publication
jobs, but several controls live in GitHub repository settings and cannot be
declared in YAML.

## Environments

Create these Actions environments:

- `automation`: allow deployment only from the default branch. Store
  `AUTOMATION_APP_PRIVATE_KEY` here, not as a repository secret.
- `release`: allow deployment only from the default branch. Add a required
  reviewer if releases should require an explicit human approval; otherwise
  keep the branch restriction so branch-dispatched workflow revisions cannot
  publish.

## Default-branch ruleset

Require the fixed `Tests`, `HACS`, and `Hassfest` status contexts, at
least one non-author approval, dismissal of stale approvals, and Code Owner
review for owned paths. `.github/CODEOWNERS` assigns workflow and dependency
automation changes to the maintainer.

Where repository workflow-execution protections are available, restrict
`workflow_dispatch` execution to maintainers.

## Releases

Enable immutable GitHub Releases in repository settings. The release workflow
also fails when a Git tag, GitHub Release, or versioned GHCR tag already exists;
it never updates a published release identity in place.
