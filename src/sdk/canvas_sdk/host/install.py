"""
Install the Canvas Tracker native messaging host.

Writes a wrapper shell script and registers the Chrome native messaging
host manifest on the current machine.

Usage:
  python -m canvas_sdk.host.install --extension-id <CHROME_EXTENSION_ID>

The extension ID is shown in chrome://extensions after loading the
unpacked extension in developer mode.
"""

import argparse
import json
import os
import platform
import stat
import sys
import textwrap
from pathlib import Path


HOST_NAME = 'com.cs3704.canvas_tracker'


def _chrome_host_dir() -> Path:
    system = platform.system()
    if system == 'Linux':
        return Path.home() / '.config' / 'google-chrome' / 'NativeMessagingHosts'
    if system == 'Darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome' / 'NativeMessagingHosts'
    if system == 'Windows':
        # Windows uses registry — not handled here, print instructions instead
        return None
    raise RuntimeError(f'Unsupported platform: {system}')


def install(extension_id: str) -> None:
    if not extension_id or len(extension_id) < 10:
        print('ERROR: provide a valid --extension-id (found in chrome://extensions)')
        sys.exit(1)

    python_exe = sys.executable
    host_dir = Path(__file__).parent

    # Write wrapper script that the manifest `path` points to
    wrapper_path = Path.home() / '.local' / 'bin' / 'canvas_tracker_host'
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text(textwrap.dedent(f"""\
        #!/bin/bash
        exec "{python_exe}" -m canvas_sdk.host "$@"
    """))
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f'Wrapper written: {wrapper_path}')

    # Write native messaging host manifest
    manifest = {
        'name': HOST_NAME,
        'description': 'Canvas Tracker native messaging host — Python SDK bridge',
        'path': str(wrapper_path),
        'type': 'stdio',
        'allowed_origins': [
            f'chrome-extension://{extension_id}/',
        ],
    }

    chrome_dir = _chrome_host_dir()
    if chrome_dir is None:
        print('Windows: register the manifest manually via regedit.')
        print('Key: HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts\\' + HOST_NAME)
        print('Value: path to the manifest JSON file')
        return

    chrome_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = chrome_dir / f'{HOST_NAME}.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f'Host manifest written: {manifest_path}')
    print(f'Host name: {HOST_NAME}')
    print('Reload the extension in chrome://extensions to pick up the change.')


def main() -> None:
    parser = argparse.ArgumentParser(description='Install Canvas Tracker native messaging host')
    parser.add_argument('--extension-id', required=True, help='Chrome extension ID from chrome://extensions')
    args = parser.parse_args()
    install(args.extension_id)


if __name__ == '__main__':
    main()
