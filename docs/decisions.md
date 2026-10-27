# Decisions

Defaults chosen without asking, with the reason. Newest at the bottom of each section.

## Environment and scope

- **D1. Repository host.** The working repository is `github.com/rahulgunwanistudy-2005/Defuse`. The product targets GitLab, so the product pipeline lives in `.gitlab-ci.yml`. A GitHub Actions workflow mirrors the lint and test stages so that every push here also has a visible, verifiable check. When the repo is mirrored to GitLab for submission, `.gitlab-ci.yml` is the pipeline of record.
- **D2. Work happens on `main`.** The owner asked for direct commits to `main`, pushed in small, reviewable steps.
- **D3. No live sandbox in this build session.** The session that produced this code had no GitLab sandbox credentials and no GCP project. The original implementation provides local fixtures and a scenario. The October 2026 review found live integration code still incomplete as well as external setup missing; see `docs/project-review.md`. Synthetic clock intervals are not live measurements. See `docs/runbook.md` for the exact commands that produce the live evidence.
- **D4. Contract fixtures are synthetic until recorded.** `engine/tests/contract/fixtures/` holds responses written from the GitLab REST and GraphQL reference, shaped exactly like real responses. `defuse workflow collect` records metadata facts; scrub and review any real recordings before replacing contract fixtures. The fixture README says which kind each file is.

## Design reference

- **D5. Visual reference.** The owner asked for the console to follow Emote Agency's "Agentix — AI Agents Landing Page" shot on Dribbble. Dribbble and its CDN are blocked from the build environment, so the direction comes from the studio's own published description of the shot: calm landscapes instead of the dark-gradient AI look, open space, modular interface elements floating over the scene, and a few focused conversion moments; plus its companion mobile app's large, scannable KPIs and modular cards. `web/DESIGN.md` records how each of those traits maps onto Defuse's incident console. If a screenshot of the shot is added to `docs/design-reference/`, the token plan should be re-checked against it.

## Completion decisions

- **D6. No paid credential manager.** Use the included local GitLab-native authority and SQLite. It handles only newly issued credentials, never existing variable contents. Other issuers need explicit local provider commands; unsupported work refuses. Existing GitLab/Duo entitlement is required and never purchased automatically.
- **D7. Model evidence is labeled.** All 22 actions execute against stateful inert transports locally. Local CPU timings and synthetic UI clocks are not live incident metrics.
- **D8. Hosting excluded.** Container and CI source is included. Actual builds need Docker; account registration, real containment runs and final public evidence remain acceptance tasks.
- **D9. Preserve SvelteKit 2.** Upgrade vulnerable dependencies within the requested framework generation. The remaining low-severity upstream advisories require a major migration; retain them visibly in the audit report.
