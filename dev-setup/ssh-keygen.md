## How to generate and use a second SSH key (Mac)

```bash
ssh-keygen -t ed25519 -b 2048 -C "<user-identity@provider.com>" -f ~/.ssh/user-identity@provider.com
```

#### Write into a new config file to use second identity:

```txt
// ~/.ssh/config

Host github
  HostName github.com
  User <user-identity>
  IdentityFile ~/.ssh/user-identity@provider.com
```

_Remark:_ Your first identity file (named id_xyz is used per default, a config entry is not necessary)

#### Add to ssh-agent

```bash
ssh-add --apple-use-keychain ~/.ssh/user-identity@provider.com
```
