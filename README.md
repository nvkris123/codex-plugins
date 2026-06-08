# Useful Codex Plugins

This repository is a Codex plugin marketplace. Add it once, then install any plugin listed here from Codex's plugin browser.

## Install

Requires:

- Codex CLI
- Python 3 for plugins that bundle Python scripts

Add this marketplace:

```bash
codex plugin marketplace add nvkris123/codex-plugins
```

Open the Codex plugin browser:

```bash
codex
/plugins
```

Choose the **Useful Codex Plugins** marketplace, then install and enable the plugin you want.

## Available Plugins

### Amazon Spending Analyzer

Analyze your Amazon order data locally.

Amazon Spending Analyzer turns Amazon's order-history export into categorized,
year-by-year files you can query or visualize. It links purchases back to
Amazon product pages when possible, separate orders into one file per year, and
optionally build a dashboard for exploring your spending patterns.

The plugin is designed to be token-efficient. Deterministic work is handled by
bundled Python scripts, and LLM tokens are used only for more ambiguous tasks,
such as resolving categories that cannot be inferred reliably from the export
alone.

#### Getting Your Amazon Order Data

The first step is to get access to your purchase history from Amazon. This is
unfortunately a manual process. Amazon does not make order-history exports
especially easy to retrieve. As of this plugin's publication, the process to
get access to your history is as follows:

1. Go to your Amazon.com account.
2. Go to **Account & Lists** -> In the dropdown click **Your Account** -> **Account**.
3. Scroll to the bottom and within **Manage Your Data** click **Request Your Data**.
4. In the box **Your orders** click **Submit Request**.

Amazon usually takes about a day to prepare the export. When it is ready, Amazon
sends ypu an email with a link to a large zip file with many confusing files inside it.
Unzip that file, then point this plugin at the unzipped folder. The plugin handles the cleanup,
categorization, yearly splitting, and dashboard generation.

It can:

- ingest an Amazon order-history export folder
- categorize purchases across your order history
- link rows back to Amazon product description pages when possible
- split orders into one categorized CSV file per year
- generate a dashboard for browsing spending patterns
- answer aggregate spending questions from the generated history

Example prompts:

```text
Use Amazon Spending Analyzer for all Amazon order export, category, spending analysis, and dashboard tasks in this session.
```

To ingest orders:
```text
Ingest "~/Downloads/Your Orders".
or
Ingest "Your Orders" for all purchases after 2018 only.
or
I have new orders downloaded to folder "Your Orders". Ingest new orders for 2026 not already ingested.
```

To create dashboard
```text
Build me an Amazon spending dashboard.
```

Other example queries:
```text
What were my biggest Amazon spending categories last year?
Compare and contrast my spend last year to this year.
```

Default generated output:

```text
amazon-history-categorized/
```

## Privacy

Plugins in this repository are designed to run local scripts where possible. Amazon Spending Analyzer keeps your Amazon export local. Its deterministic ingestion, analysis, and dashboard scripts do not call an LLM, Codex CLI, or an API.

If you ask Codex to resolve ambiguous categories, Codex should read only the generated review CSV rows and write category decisions back through the bundled helper script.

Do not share generated output folders such as `amazon-history-categorized/`; they contain personal purchase history.

## Marketplace Structure

```text
.agents/plugins/marketplace.json
plugins/
  amazon-spending-analyzer/
    .codex-plugin/plugin.json
    skills/
    scripts/
```

## Troubleshooting

List configured marketplaces:

```bash
codex plugin marketplace list
```

Refresh marketplaces:

```bash
codex plugin marketplace upgrade
```

If a plugin does not appear, restart Codex and open `/plugins` again.

## License

MIT
