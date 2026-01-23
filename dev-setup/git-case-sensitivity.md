# macOS Developer Volume Setup (Case-Sensitive, Linux-like)

This guide describes how to create and use a **separate, case‑sensitive APFS volume** on macOS for development, to better emulate a typical Linux filesystem behavior.

## Why a Separate Case-Sensitive Volume?

- Most standard macOS installations use a **case-insensitive** APFS volume (e.g. `File.txt` and `file.txt` are treated as the same file).
- Many Linux systems use a **case-sensitive** filesystem.
- Some tools, build systems, or projects assume case sensitivity and can behave differently (or break) on a case-insensitive filesystem.
- By creating a separate **APFS (Case-sensitive)** volume, you can:
  - Work in an environment closer to Linux.
  - Avoid unexpected issues with case collisions in filenames.

---

## 1. Create a Case-Sensitive APFS Volume

1. Open **Disk Utility** (`/Applications/Utilities/Disk Utility.app`).
2. In the menu, choose **View → Show All Devices**.
3. Select your main **APFS container** (usually something like _Container disk1_).
4. Click the **“+” (Add Volume)** button in the toolbar.
5. Use the following settings:
   - **Name**: `Developer`
   - **Format**: `APFS (Case-sensitive)` -> Choose `(Case-sensitive, encrypted)` for work devices
   - **Role**: `None` (default is fine)
6. Click **Add**.

After creation, macOS will mount it under `/Volumes/Developer` by default. If it appears under a different path, you can rename it in Finder or Disk Utility so that the mount point becomes `/Volumes/Developer`.

---

## 2. Prepare the Developer Directory Structure

Once the volume is mounted at `/Volumes/Developer`, create a directory to hold your projects:

```bash
mkdir -p /Volumes/Developer/Developer
```

## 3. Create a Convenient Symlink in Your Home Directory

To make navigation easier, create a symlink in your home directory that points to the developer folder on the case‑sensitive volume:

```bash
ln -s /Volumes/Developer/Developer ~/Developer
```

After this, you can simply `cd ~/Developer` to work on your projects.
Tools and editors configured to use `~/Developer` will transparently use the case‑sensitive volume.
If `~/Developer` already exists and is a directory, remove or rename it first:

```bash
rm -rf ~/Developer    # Be careful: this deletes the existing folder!
ln -s /Volumes/Developer/Developer ~/Developer
```

## 4. Configure Git to Respect Case Sensitivity

By default, Git on macOS may treat file names as case-insensitive, which conflicts with the behavior you expect on a Linux-like system. To align Git behavior more closely with a case‑sensitive Linux setup, set:

```bash
git config --global core.ignorecase false
```
