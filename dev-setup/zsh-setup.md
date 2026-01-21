## ZSH Setup (TBD more precisely)

#### I am using nvm (installed via homebrew), pyenv and starship

To add, add this to your `~/.zshrc`

```bash
export NVM_DIR="$HOME/.nvm"
  [ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"  # This loads nvm
  [ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"  # This loads nvm bash_completion
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - zsh)"
eval "$(starship init zsh)"
```

#### I am using a user local bin folder

Add this to your `~/.zshrc`

```bash
export PATH="$HOME/.local/bin:$PATH"
```

#### Use symlink to add code to $PATH

```bash
ln -s "~/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" "$HOME/.local/bin/code"
```
