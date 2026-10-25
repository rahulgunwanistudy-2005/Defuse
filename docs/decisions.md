# Decisions

Defaults chosen without asking, with the reason. Newest at the bottom of each section.

## Environment and scope

- **D1. Repository host.** The working repository is `github.com/rahulgunwanistudy-2005/Defuse`. The product targets GitLab, so the product pipeline lives in `.gitlab-ci.yml`. A GitHub Actions workflow mirrors the lint and test stages so that every push here also has a visible, verifiable check. When the repo is mirrored to GitLab for submission, `.gitlab-ci.yml` is the pipeline of record.
- **D2. Work happens on `main`.** The owner asked for direct commits to `main`, pushed in small, reviewable steps.
- **D3. No live sandbox in this build session.** The session that produced this code had no GitLab sandbox credentials and no GCP project. Everything that needs them (recorded API fixtures, the three containment runs, Cloud Run URLs, timings) is built, wired and tested against fixtures, and the README marks every number that still needs a live run as pending. No number in this repository is invented. See `docs/runbook.md` for the exact commands that produce the live evidence.
- **D4. Contract fixtures are synthetic until recorded.** `engine/tests/contract/fixtures/` holds responses written from the GitLab REST and GraphQL reference, shaped exactly like real responses. `defuse fixtures record` replaces them with scrubbed recordings from the sandbox. The fixture README says which kind each file is.

## Design reference

- **D5. Visual reference.** The owner asked for the console to follow Emote Agency's "Agentix — AI Agents Landing Page" shot on Dribbble. Dribbble and its CDN are blocked from the build environment, so the direction comes from the studio's own published description of the shot: calm landscapes instead of the dark-gradient AI look, open space, modular interface elements floating over the scene, and a few focused conversion moments; plus its companion mobile app's large, scannable KPIs and modular cards. `web/DESIGN.md` records how each of those traits maps onto Defuse's incident console. If a screenshot of the shot is added to `docs/design-reference/`, the token plan should be re-checked against it.
