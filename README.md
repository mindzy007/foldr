# Foldr

Change Windows folder icons in a couple of clicks.

Drop in your folders, pick an icon, and press **Apply**. Foldr sets the icon without admin rights and refreshes Explorer for you. Press **Reset** to put the default icons back.

## Features

- Drag and drop folders, or use **Add folder**
- Icon library with color palettes, sorting, and adjustable icon size
- Optional subfolders and hidden folders
- One-click **Reset** to restore default icons
- Built-in update check that pulls the latest release from GitHub

## Install

1. Download `Foldr-Setup-<version>.exe` from the [latest release](https://github.com/mindzy007/foldr/releases/latest).
2. Run it and follow the steps. Foldr installs to a folder your user can write to, so no admin rights are needed.

## Run from source

Requires Windows and Python 3.

```bat
python -m pip install -r requirements.txt
python foldr.py
```

Or just double-click `run.bat`.

## Build the installer

```bat
build.bat
```

This creates `dist\Foldr-Setup-<version>.exe`. The version comes from `version.py`.

## Releasing

1. Bump `APP_VERSION` in `version.py`.
2. Run `build.bat`.
3. Create a GitHub release whose tag matches the version (without a `v`) and attach the installer.

Foldr compares its own version against the latest release tag to offer updates.

## Project layout

| File | Purpose |
| --- | --- |
| `foldr.py` | The app and its UI |
| `core.py` | Folder icon logic |
| `installer.py` | The setup wizard |
| `version.py` | Current version |
| `assets/` | Icon library |
| `fonts/` | Bundled fonts |

## Notes

Foldr saves `window_size.json` and `settings.json` next to the installed executable, so keep the install folder writable.
