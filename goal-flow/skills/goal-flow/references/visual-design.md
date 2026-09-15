# Visual Design Protocol

Use visual design to make consequential relationships inspectable before coding, not to decorate a plan.

## Source and viewer

`design/architecture.drawio` is the editable, multi-page source of truth. `design/architecture.html` is a generated review surface that loads the official diagrams.net viewer. Regenerate it with `design-render` after editing the source. The viewer needs network access to load the diagrams.net JavaScript; the `.drawio` file remains usable offline in diagrams.net desktop or another compatible editor.

Open the HTML in a Codex browser/file preview when possible. If the browser requires HTTP, serve only the goal's design directory with a short-lived local static server and open its localhost URL. Do not upload private repository diagrams merely to obtain a share link.

## Minimum visual contract

Keep two mandatory pages:

1. `Architecture`: for an existing system, show current state, proposed change, target state, external actors/systems, important boundaries, and non-goals. For greenfield, replace current state with the v1 system boundary and show deferred capabilities.
2. `Critical data flow`: show the main trigger, validation/transformation, stores or services, response/side effects, and the important failure, retry, or rollback path. Label arrows with the data or contract crossing the boundary.

Add a page only when it resolves an otherwise hard-to-see decision:

- frontend interaction/state flow;
- backend service or request sequence;
- data model, ownership, retention, or migration;
- deployment/runtime topology;
- trust, authorization, or failure boundaries.

## Editing rules

Replace every scaffold placeholder with project-specific content. Prefer names from the repository and link diagram elements to requirement IDs or file/module names when that improves traceability. Distinguish facts, proposed changes, external dependencies, and deferred scope through labels and a small legend; color alone is insufficient.

Run `design-check` before approval. The controller freezes normalized page, node, label, connection, and semantic metadata content. Geometry and styling are deliberately excluded, so moving or recoloring shapes remains editable after approval. Changing a component, label, connection, page meaning, or `data-*` metadata is a semantic change and requires `replan` once approved.

The drawing explains structure and flow; `goal.md` remains the concise textual contract for outcome, decisions, non-goals, acceptance criteria, verifier commands, and risks. Do not duplicate every paragraph into the drawing.
