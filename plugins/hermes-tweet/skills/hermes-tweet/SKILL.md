---
name: hermes-tweet
description: Use Hermes Agent for X/Twitter social research, monitoring, exports, and approval-gated actions through Xquik. Trigger when the user asks to search X/Twitter, read replies, inspect profiles, monitor posts, export followers, prepare posts, or install the Hermes Tweet plugin.
---

# Hermes Tweet

Use Hermes Tweet when the user wants Hermes Agent to work with X/Twitter through
Xquik.

## Install

Install and enable the published Hermes Agent plugin:

```bash
hermes plugins install Xquik-dev/hermes-tweet --enable
```

For PyPI installs, use:

```bash
uv pip install --python ~/.hermes/hermes-agent/venv/bin/python hermes-tweet
hermes plugins enable hermes-tweet
```

## Configure

Set an API key from the Xquik dashboard:

```bash
export XQUIK_API_KEY="xq_..."
```

Keep account-changing actions disabled unless the user explicitly requests them:

```bash
export HERMES_TWEET_ENABLE_ACTIONS="false"
```

## Use

Start with `tweet_explore` to inspect the available route catalog.

Use `tweet_read` for:

- tweet search and thread reads
- reply and profile research
- monitoring and exports
- trend, support, launch, and audit workflows

Use `tweet_action` only when the user explicitly asks for posting, replies,
DMs, follows, monitor changes, webhook changes, media changes, extraction jobs,
or draw actions and `HERMES_TWEET_ENABLE_ACTIONS=true`.

Do not paste API keys into prompts, issues, pull requests, or docs.
