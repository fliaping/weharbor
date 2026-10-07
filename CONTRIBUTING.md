# Contributing

Start with README.md and AGENTS.md. Keep the integration layer small and reuse
the pinned upstream base image. Component upgrades should update
versions.lock.json, Dockerfile defaults and documentation together.

Run python3 scripts/check.py for source changes. For container or startup changes,
also build the image and run scripts/smoke-test.sh against an empty test profile.
Keep tests focused on behavior such as authentication, package integrity and
preservation of existing settings.

Issue reports should include component versions, expected behavior and a small
reproduction. Remove account identifiers, message contents, API tokens, passwords
and database keys from logs before sharing them.
