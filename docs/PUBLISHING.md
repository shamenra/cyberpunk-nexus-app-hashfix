# Publishing this repository on GitHub

**Do not publish the `.work/` directory.** It is intentionally excluded by `.gitignore` and can contain game install paths, local logs, backups and generated databases.

## Before publishing

1. Review the files and verify no private paths, tokens, game files or account information were added.
2. Run the local tests: `python3 -m unittest discover -s tests -v`.
3. Run `./cyberpunk-hashfix --help` and read the README's experimental-status notice.
4. Do not attach a `game_hashes_db.zip` generated from your PC. The repository is meant to let people build their **own** database from their own Steam files.
5. Include a release note explaining that the original repair method worked on Steam build `26161058` but the new wrapper is still experimental.

## GitHub CLI (one method)

Install and authenticate GitHub CLI (`gh`) using your preferred distribution package or GitHub's instructions. From the **root of this repository**, run:

```bash
git init -b main
git add README.md LICENSE CHANGELOG.md CONTRIBUTING.md .gitignore .github docs scripts src tests cyberpunk-hashfix
git commit -m "Initial Cyberpunk Nexus Mods App hashfix release"

gh auth login
gh repo create cyberpunk-nexus-app-hashfix --public --source=. --remote=origin --push
```

Review the created repository in GitHub's web UI. Do not use `git add .` if you have dropped private files into the root.

If you prefer GitHub's website, create a new **empty public** repository named `cyberpunk-nexus-app-hashfix`, then follow the push commands GitHub shows. Do **not** add a separate README/license on GitHub first if you already have them here.

## Suggested first GitHub release

Tag: `v0.1.0-experimental`

Notes: Steam/Linux-only workaround for the discontinued Nexus Mods App. Original method verified for Cyberpunk 2077 2.5, Steam build 26161058; newly generalized build wrapper requires community testing. Does not fix outdated mods or replace the AppImage. No game assets or database files distributed.

## Where to share it

Post a concise explanation on relevant Nexus App GitHub issues, community discussion threads, or Linux Cyberpunk modding posts, **if those places allow links**. Avoid spamming multiple issues with the same comment, and disclose that you are the maintainer. Refer users to the README and troubleshooting guide rather than promising a universal fix.

See [COMMENT_TEMPLATE.md](COMMENT_TEMPLATE.md) for a ready-to-edit comment. Replace the placeholder with your actual repository URL after publication.
