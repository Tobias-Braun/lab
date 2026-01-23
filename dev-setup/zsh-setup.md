# ZSH Setup Guide

## 1. Configure Autocomplete with `compinstall`

After installing `zsh` or when configuring your terminal, run:

```bash
compinstall # this installs and configures the zsh autocomplete
```

This opens an interactive configuration to set up completion behavior.

---

## 2. Enable Forward-Delete-Word

To enable a keybinding for “forward delete word” in `zsh`, add this to your `~/.zshrc`:

```bash
# KEY BINDINGS
bindkey '^[[3;3~' kill-word
```

Reload your shell (e.g. `exec zsh` or open a new terminal) to apply the change.

---

## 3. Configure `nvm` (Homebrew), `pyenv` and `starship`

If you are using `nvm` (installed via Homebrew), `pyenv`, and `starship`, add this to your `~/.zshrc`:

```bash
export NVM_DIR="$HOME/.nvm"
  [ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"  # This loads nvm
  [ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"  # This loads nvm bash_completion

export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - zsh)"

eval "$(starship init zsh)"
```

Again, reload `zsh` after editing your config.

---

## 4. Use a User-Local `bin` Folder

To use a local `bin` folder (e.g. for custom scripts and symlinks), add this to your `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Ensure the directory exists:

```bash
mkdir -p ~/.local/bin
```

---

## 5. Add VS Code `code` Command via Symlink

If `code` is not on your `PATH`, create a symlink into your local `bin`:

```bash
ln -s "$HOME/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" "$HOME/.local/bin/code"
```

> Note: Adjust the path to the VS Code app if it lives in `/Applications` instead of `~/Applications`.

After that, you should be able to run:

```bash
code .
```

from any project directory.
