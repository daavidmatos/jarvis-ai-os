# JARVIS Desktop Companion

The Desktop Companion is the local half of JARVIS computer collaboration. The JARVIS server can stay in the cloud while the companion runs on the user's computer and exposes a bounded, authenticated bridge to local creative applications.

## What works in this version

- Persistent authenticated WebSocket connection to `/ws/desktop-bridge`.
- Linux/Windows/macOS process discovery for supported visual applications (best-effort; Linux is the primary tested target).
- Optional bounded screen capture for visual review. Screenshots are **off by default** and must be explicitly enabled once.
- Private frame transport: frames are sent through the authenticated bridge, kept in a rolling server-side window, and can be passed directly to the OpenAI vision-capable primary model without a public screenshot URL.
- Live workbench state updates and command-result reporting.
- **Blender write adapter**: current scene/object/camera/render state plus allow-listed structured actions.
- Automatic Linux user service (`systemd --user`) so the bridge restarts on login.
- Photoshop, Illustrator, Premiere, After Effects and Figma can be detected and visually inspected when screenshots are enabled, but write adapters are not yet implemented. JARVIS must report that limitation instead of pretending it edited them.

## Safety boundary

The companion never executes arbitrary shell commands or arbitrary Python from the JARVIS server. A user/mission authorizes a semantic change, the cloud planner translates it into an allow-listed structured action, and the local adapter validates/executes only that action.

The Blender adapter currently allows:

- inspect scene
- select object
- set/nudge object transform
- change camera lens
- add a bounded primitive
- change render resolution
- render a preview
- save the already-named project
- undo

It does **not** execute arbitrary Python, shell commands, delete files, read credentials, or save an Untitled project to an invented path.

## Local install (Ubuntu/Linux)

From the JARVIS repository and activated `.venv`:

```bash
python -m pip install -r requirements-desktop.txt
```

For a local server:

```bash
python -m desktop_companion configure --server http://localhost:8000 --screenshots
```

For a hosted server, set a strong `DESKTOP_BRIDGE_TOKEN` in the server environment and configure the companion with the same value. Prefer entering it only on the local machine. Remote plain HTTP/WS is refused by default; use HTTPS/WSS.

Install the Blender add-on:

```bash
python -m desktop_companion install-blender-addon
```

Then restart Blender and enable **JARVIS Desktop Bridge** in `Preferences > Add-ons`.

Test the local status:

```bash
python -m desktop_companion status
```

Run it in the foreground:

```bash
python -m desktop_companion run
```

Or install it as a persistent Linux user service:

```bash
python -m desktop_companion install-service
```

The service uses the current virtual-environment Python and restarts automatically after temporary network failures.

## Privacy

Screen capture is opt-in because a whole-monitor screenshot can contain unrelated sensitive information. When enabled, the companion captures only while a supported visual application is detected, downsizes frames, JPEG-compresses them, and the server retains only a small rolling window. Disabling screenshots still leaves structured Blender state available.

## Computer-off behavior

Cloud-only tasks (Gmail, Calendar, Google Ads, web research, etc.) can continue when the user's computer is off. Local Blender/Photoshop/etc. inspection or control cannot: the Desktop Companion and the target application must be running on that computer.
