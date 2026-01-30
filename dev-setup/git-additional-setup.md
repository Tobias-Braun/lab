## How to have your own local .gitignore

Sometimes you want to ignore files in git which are specific to your workflow.
This helps you configure your own local .gitignore for your repo:

https://stackoverflow.com/questions/1753070/how-do-i-configure-git-to-ignore-some-files-locally

## Auto-Setup branches

Instead of having to manually create an upstream branch you want to push to by using this command

```bash
git push --set-upstream origin new-branch
```

You can let git autoSetup the remote branch with his config entry:

```bash
git config --global push.autoSetupRemote true
```
