# Uninstall AYUAKSHU Audio

## Remove the application

1. Quit AYUAKSHU Audio.
2. Move `/Applications/AYUAKSHU Audio.app` (or your install location) to Trash.

Removing the `.app` does **not** delete your local project data or models.

## Optional: delete application data

**Warning:** deleting application support removes projects, voices, generated audio, and local models (~3 GB).

```text
~/Library/Application Support/AYUAKSHU Audio/
```

```bash
rm -rf "$HOME/Library/Application Support/AYUAKSHU Audio"
```

Legacy installs may also have used:

```text
~/Library/Application Support/OfflineVoice/
```

## Privacy note

AYUAKSHU Audio does not use cloud accounts. Uninstalling the app and deleting
Application Support removes local voice and project data from this Mac.
