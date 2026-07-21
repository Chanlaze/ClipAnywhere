# ClipAnywhere

Python clipboard sync for several PCs, including text and copied files.

## Network Shape

Your office PC can only use HTTP port 80 through:

```text
http://autoproxy:8088/
```

Your NAS already owns public port 80 for a website, so run the Python server on an internal NAS port, then reverse-proxy one URL path from the existing website:

```text
http://chanlaze.ddns.net/clipanywhere/
```

Example flow:

```text
Client PC -> office proxy -> http://chanlaze.ddns.net:80/clipanywhere -> NAS web server -> Python server localhost:8765
```

## Files

- `clipanywhere/server.py`: NAS sync server.
- `clipanywhere/client.py`: Windows/macOS client sync loop.
- `clipanywhere/clipboard_windows.py`: Windows clipboard text/file access.
- `clipanywhere/clipboard_macos.py`: macOS clipboard text/file access.
- `server_config.example.json`: server config.
- `server_config.docker.example.json`: NAS Docker server config.
- `Dockerfile` and `docker-compose.yml`: NAS Docker packaging.
- `client_config.example.json`: office PC client config using the proxy.
- `client_config.direct.example.json`: client config for PCs without a proxy.
- `client_config.macos.example.json`: macOS client config.

## Install

Python 3.10+ is recommended.

On Windows clients:

```powershell
pip install -r requirements.txt
```

On macOS clients, no extra pip packages are needed for the current client.

On NAS, the server only uses Python standard library.

## Server

Copy `server_config.example.json` to `server_config.json` and edit the token.

```powershell
python -m clipanywhere.server --config server_config.json
```

By default it listens on `127.0.0.1:8765`.

## NAS Docker Server

If your Synology NAS has Container Manager or Docker, this is the easiest setup.

Copy the project folder to the NAS, for example:

```bash
/volume1/docker/ClipAnywhere
```

Create the Docker config:

```bash
cd /volume1/docker/ClipAnywhere
cp server_config.docker.example.json server_config.json
```

Edit `server_config.json` and replace:

```json
"token": "change-this-long-random-token"
```

with a long private token. Use the same token on every client PC.

Build and start the container:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
docker logs clipanywhere
```

The container listens inside Docker on `0.0.0.0:8765`, but `docker-compose.yml` publishes it only on the NAS loopback address:

```text
127.0.0.1:8765
```

That means the Synology reverse proxy can reach it, but the Python server port is not directly open to your LAN or the internet.

To update after copying newer files to the NAS:

```bash
docker compose up -d --build
```

## Reverse Proxy

Configure your existing NAS website to proxy:

```text
/clipanywhere/ -> http://127.0.0.1:8765/
```

Important headers:

```text
X-Forwarded-Prefix: /clipanywhere
X-Forwarded-Proto: http
```

Synology DSM usually lets you do this through **Login Portal / Application Portal -> Reverse Proxy**:

- Source protocol: `HTTP`
- Source hostname: `chanlaze.ddns.net`
- Source port: `80`
- Source path: `/clipanywhere`
- Destination protocol: `HTTP`
- Destination hostname: `127.0.0.1`
- Destination port: `8765`

Keep the Python server bound to `127.0.0.1` if it runs on the NAS itself. That keeps it private behind the NAS web server.

## Client

Copy `client_config.example.json` to `client_config.json` and edit:

- `server_url`: `http://chanlaze.ddns.net/clipanywhere`
- `token`: same as server
- `device_name`: unique per PC
- `proxy.username` and `proxy.password` if needed

For PCs that connect directly, copy `client_config.direct.example.json` instead.

Then run:

```powershell
python -m clipanywhere.client --config client_config.json
```

If your Windows PC uses an embedded/custom Python that cannot find the `clipanywhere` module, run the included launcher instead:

```powershell
C:\python\python.exe .\start_client.py --config .\client_config.json
```

Or double-click:

```text
start_client.bat
```

To run hidden in the Windows system tray, double-click:

```text
start_client_tray.bat
```

The tray launcher uses the project icon at:

```text
assets/clipanywhere.ico
```

The tray launcher writes client output to:

```text
clipanywhere_client.log
```

Right-click the tray icon to open the log or exit ClipAnywhere.

If the tray icon does not appear, first check the hidden tray icons arrow `^` near the Windows clock. Also check:

```text
clipanywhere_tray_launch.log
clipanywhere_tray.log
clipanywhere_client.log
```

The client window prints clipboard status messages such as:

```text
Status: press Ctrl+Alt+C to ClipAnywhere-copy and sync
Text being sync: uploading 42 characters
Files/Folder being sync: uploading 1 folder (Reports)
Files/Folder downloaded: 1 folder (Reports)
Files/Folder placed on clipboard, ready for Ctrl+V
```

On Windows, normal `Ctrl+C` stays local and does not sync. Use `Ctrl+Alt+C` when you want ClipAnywhere to copy the current selection and sync it to other PCs.

To manually put an already downloaded file or folder onto the Windows clipboard for testing:

```powershell
C:\python\python.exe .\copy_to_clipboard.py ".\ClipAnywhereDownloads\some-downloaded-folder"
```

Then paste with `Ctrl+V` in File Explorer.

## macOS Client

On the Mac, copy `client_config.macos.example.json` to `client_config.json` and edit:

- `server_url`: `http://chanlazenas.ddns.net`
- `token`: same as server
- `device_name`: unique name, such as `macbook`

Run:

```bash
python3 start_client.py --config client_config.json
```

You can also run the included launcher:

```bash
chmod +x start_client.command
./start_client.command
```

Text uses `pbcopy`/`pbpaste`. File and folder clipboard support uses macOS AppleScript/Finder pasteboard data, so copied files/folders from Finder can sync and downloaded files/folders are placed back onto the Mac clipboard for paste.

The global `Ctrl+Alt+C` hotkey is currently implemented for Windows. The macOS client can receive synced clipboard data, and macOS send support still requires starting from clipboard content already copied on that Mac.

## Current Limits

This MVP is intentionally simple:

- Last writer wins.
- Files are uploaded as a zip archive.
- The client polls instead of keeping a permanent websocket open, which works better with restrictive office proxies.
- Clipboard file sync supports Windows via `pywin32` and macOS via built-in pasteboard commands.

## Security Notes

- Use a long random token. Anyone with the token can read and write the shared clipboard.
- The office constraint means this is plain HTTP on port 80 unless your proxy also permits HTTPS on port 443.
- Do not expose the Python server port directly to the internet; expose only the reverse-proxied `/clipanywhere` path.
