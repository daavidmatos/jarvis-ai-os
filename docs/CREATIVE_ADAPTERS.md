# JARVIS Creative Editor Adapters

JARVIS separates **seeing an application** from **editing it**. A screen observer can provide visual context, but write operations only go to a dedicated adapter that advertises `adapter.write=true` and exposes a bounded action set.

## Current write adapters

| Application | Read/live state | Structured edits | High-level creation |
| --- | --- | --- | --- |
| Blender | Yes | Yes | primitives, camera, render setup |
| Figma | Yes | Yes | landing-page mockup, frames, text, shapes |
| Photoshop | Yes | Yes | documents, text, vector rectangles, marketing canvas |
| Illustrator | Yes | Yes | documents, artboards, text, vector shapes, landing mockup |
| After Effects | Yes | Yes | comps, text, solids, rectangles, transforms, position keyframes, marketing comp |

Premiere remains visual/read-only until its dedicated write adapter is added.

## Safety model

The server never sends arbitrary Python, JavaScript, JSX, ExtendScript, shell, or `eval` payloads to an editor. Natural-language requests are converted by `jarvis.desktop_actions.DesktopActionPlanner` into one allow-listed action plus validated arguments.

Examples:

- `crie um cubo no Blender` -> `add_primitive`
- `crie uma landing page para um creme no Figma` -> `create_landing_page`
- `crie um post 1080x1350 no Photoshop` -> `create_marketing_canvas`
- `monte um mockup vetorial no Illustrator` -> `create_landing_mockup`
- `crie uma composição vertical de lançamento no After Effects` -> `create_marketing_comp`

In collaborative mode, an explicit request authorizes one edit. In Mission mode, `allow_computer_control` must be granted for the mission before JARVIS can perform a sequence of creative-app edits.

## Figma

Adapter: `creative_adapters/figma/`

The plugin uses Figma's Plugin API directly. It can create/update nodes in the current file and opens a persistent JARVIS panel while the plugin is running.

Development setup:

1. In Figma, create/import a development plugin using `creative_adapters/figma/manifest.json`.
2. Open the plugin panel.
3. Enter the JARVIS HTTPS server and Desktop Bridge token once.
4. Connect.

The development manifest currently permits a user-configured network domain. Restrict `networkAccess.allowedDomains` to the deployed JARVIS hostname before publishing/distributing the plugin.

## Photoshop

Adapter: `creative_adapters/photoshop/`

This is a UXP panel. It uses Photoshop DOM APIs for document/text/layer operations and `batchPlay` only for the bounded rectangle shape operation.

Development setup:

1. Load `creative_adapters/photoshop/manifest.json` with Adobe UXP Developer Tool.
2. Open the JARVIS panel in Photoshop.
3. Configure the JARVIS server and Desktop Bridge token once.
4. Connect.

The development manifest uses broad network permission because the final private hostname is not known yet. Restrict it to the deployed JARVIS WSS hostname before distribution.

## Illustrator + After Effects

Adapter: `creative_adapters/adobe_cep/`

A CEP panel is shared by both applications. `jsx/bridge.jsx` exposes fixed functions that perform only known structured actions. The panel sends scalar arguments through an encoded key/value format; it never evaluates server-provided source code.

Development setup requires loading the CEP extension in a supported Adobe development environment. Once loaded, open **JARVIS**, configure the server/token, and connect.

## Blender

The existing Desktop Companion + Blender add-on remains the Blender write path. It uses private local IPC and the same structured action planner.

## Platform note

Editor adapters only work on a computer where the corresponding editor itself can run. JARVIS can remain hosted in the cloud; the editor plugin/bridge is local to the computer that owns the open project.

This means a user can talk to the cloud/mobile JARVIS while the workstation is online, and the authorized edit is routed to the correct live editor adapter.
