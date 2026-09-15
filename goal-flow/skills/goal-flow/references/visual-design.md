# Visual Design Protocol

Use visual design to make consequential relationships inspectable before coding, not to decorate a plan.

## Source and viewer

`design/architecture.drawio` is the editable, multi-page source of truth. `design/architecture.html` is a generated review surface that loads the official diagrams.net viewer. Regenerate it with `design-render` after editing the source. The viewer needs network access to load the diagrams.net JavaScript; the `.drawio` file remains usable offline in diagrams.net desktop or another compatible editor.

Open the HTML in a Codex browser/file preview when possible. If the browser requires HTTP, serve only the goal's design directory with a short-lived local static server and open its localhost URL. Do not upload private repository diagrams merely to obtain a share link.

## Minimum visual contract

Keep two mandatory pages:

1. `Architecture`: for an existing system, show current state, proposed change, target state, external actors/systems, important boundaries, and non-goals. For greenfield, replace current state with the v1 system boundary and show deferred capabilities.
2. `Critical data flow`: show the main trigger, validation/transformation, stores or services, response/side effects, and the important failure, retry, or rollback path. Label arrows with the data or contract crossing the boundary.

Every non-trivial node and edge must carry editable `data-*` metadata. Nodes identify their kind, responsibility, requirement IDs, and existing/new/changed/deferred status. Every cross-boundary edge has a stable protocol ID. A visible protocol card for that ID explains the transport, request and response schemas, errors, authentication, timeout, retry, and idempotency. Field-level details include at least name, type, requiredness, validation, and business meaning for identifiers, status, time, money, permissions, sensitive data, and branch-driving fields.

The overview stays readable: put a short protocol summary on the edge and the complete contract in a linked card or detail page in the same Draw.io file. The generated HTML viewer should expose the same cards when a node or edge is selected. A visual plan is not approval-ready when it only has generic component names, disconnected arrows, or protocol IDs without visible field and failure details.

Add a page only when it resolves an otherwise hard-to-see decision:

- frontend interaction/state flow;
- backend service or request sequence;
- data model, ownership, retention, or migration;
- deployment/runtime topology;
- trust, authorization, or failure boundaries.

For interface, event, schema, or persistence changes, a protocol/data-contract page or card is mandatory. For UI state changes, add the frontend interaction page; for asynchronous, multi-service, or transactional paths, add the backend sequence and failure/compensation detail. Keep the number of pages proportional to the decision surface.

## Editing rules

Replace every scaffold placeholder with project-specific content. Prefer names from the repository and link diagram elements to requirement IDs or file/module names when that improves traceability. Distinguish facts, proposed changes, external dependencies, and deferred scope through labels and a small legend; color alone is insufficient.

Run `design-check` before approval. The controller validates unique IDs, parent and edge references, end-to-end flow connectivity, required node kinds, protocol cards, visible contract fields, and requirement coverage. It freezes normalized page, node, label, connection, semantic metadata, and semantic style content. Geometry and purely cosmetic styling remain editable after approval; changing a component, label, connection, page meaning, protocol field, arrow direction, or `data-*` metadata is a semantic change and requires `replan` once approved. Regenerate `architecture.html` after edits and do not approve while its source semantic hash is stale.

The drawing explains structure and flow; `goal.md` remains the concise textual contract for outcome, decisions, non-goals, acceptance criteria, verifier commands, and risks. Do not duplicate every paragraph into the drawing.
