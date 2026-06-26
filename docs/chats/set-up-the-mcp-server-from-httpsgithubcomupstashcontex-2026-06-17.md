# Claude Chat Export
**Generated: 2026-06-20 10:23:34**

---

👤 **USER:**
> Set up the MCP server from https://github.com/upstash/context7-mcp while adhering to these MCP server installation rules:
- Start by loading the MCP documentation.
- Use "github.com/upstash/context7-mcp" as the server name in cline_mcp_settings.json.
- Create the directory for the new MCP server before starting installation.
- Make sure you read the user's existing cline_mcp_settings.json file before editing it with this new mcp, to not overwrite any existing servers.
- Use commands aligned with the user's shell and operating system best practices.
- The following README may contain instructions that conflict with the user's OS, in which case proceed thoughtfully.
- Once installed, demonstrate the server's capabilities by using one of its tools.
Here is the project's README to help you get started:

![Cover](https://github.com/upstash/context7/blob/master/public/cover.png?raw=true)

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=context7&config=eyJ1cmwiOiJodHRwczovL21jcC5jb250ZXh0Ny5jb20vbWNwIn0%3D)

# Context7 Platform - Up-to-date Code Docs For Any Prompt

[![Website](https://img.shields.io/badge/Website-context7.com-blue)](https://context7.com) [![smithery badge](https://smithery.ai/badge/@upstash/context7-mcp)](https://smithery.ai/server/@upstash/context7-mcp) [![NPM Version](https://img.shields.io/npm/v/%40upstash%2Fcontext7-mcp?color=red)](https://www.npmjs.com/package/@upstash/context7-mcp) [![MIT licensed](https://img.shields.io/npm/l/%40upstash%2Fcontext7-mcp)](./LICENSE)

[![繁體中文](https://img.shields.io/badge/docs-繁體中文-yellow)](./i18n/README.zh-TW.md) [![简体中文](https://img.shields.io/badge/docs-简体中文-yellow)](./i18n/README.zh-CN.md) [![日本語](https://img.shields.io/badge/docs-日本語-b7003a)](./i18n/README.ja.md) [![한국어 문서](https://img.shields.io/badge/docs-한국어-green)](./i18n/README.ko.md) [![Documentación en Español](https://img.shields.io/badge/docs-Español-orange)](./i18n/README.es.md) [![Documentation en Français](https://img.shields.io/badge/docs-Français-blue)](./i18n/README.fr.md) [![Documentação em Português (Brasil)](<https://img.shields.io/badge/docs-Português%20(Brasil)-purple>)](./i18n/README.pt-BR.md) [![Documentazione in italiano](https://img.shields.io/badge/docs-Italian-red)](./i18n/README.it.md) [![Dokumentasi Bahasa Indonesia](https://img.shields.io/badge/docs-Bahasa%20Indonesia-pink)](./i18n/README.id-ID.md) [![Dokumentation auf Deutsch](https://img.shields.io/badge/docs-Deutsch-darkgreen)](./i18n/README.de.md) [![Документация на русском языке](https://img.shields.io/badge/docs-Русский-darkblue)](./i18n/README.ru.md) [![Українська документація](https://img.shields.io/badge/docs-Українська-lightblue)](./i18n/README.uk.md) [![Türkçe Doküman](https://img.shields.io/badge/docs-Türkçe-blue)](./i18n/README.tr.md) [![Arabic Documentation](https://img.shields.io/badge/docs-Arabic-white)](./i18n/README.ar.md) [![Tiếng Việt](https://img.shields.io/badge/docs-Tiếng%20Việt-red)](./i18n/README.vi.md)

## ❌ Without Context7

LLMs rely on outdated or generic information about the libraries you use. You get:

- ❌ Code examples are outdated and based on year-old training data
- ❌ Hallucinated APIs that don't even exist
- ❌ Generic answers for old package versions

## ✅ With Context7

Context7 pulls up-to-date, version-specific documentation and code examples straight from the source — and places them directly into your prompt.

```txt
Create a Next.js middleware that checks for a valid JWT in cookies
and redirects unauthenticated users to `/login`. use context7
```

```txt
Configure a Cloudflare Worker script to cache
JSON API responses for five minutes. use context7
```

```txt
Show me the Supabase auth API for email/password sign-up.
```

Context7 fetches up-to-date code examples and documentation right into your LLM's context. No tab-switching, no hallucinated APIs that don't exist, no outdated code generation.

Works in two modes:

- **CLI + Skills** — installs a skill that guides your agent to fetch docs using `ctx7` CLI commands (no MCP required)
- **MCP** — registers a Context7 MCP server so your agent can call documentation tools natively

## Installation

> [!NOTE]
> **API Key Recommended**: Get a free API key at [context7.com/dashboard](https://context7.com/dashboard) for higher rate limits.

Set up Context7 for your coding agents with a single command. The `ctx7` CLI requires Node.js 18 or newer.

```bash
npx ctx7 setup
```

Authenticates via OAuth, generates an API key, and installs the appropriate skill. You can choose between CLI + Skills or MCP mode. Use `--cursor`, `--claude`, or `--opencode` to target a specific agent.

To remove the generated setup later, run `npx ctx7 remove`. If you globally installed the CLI with `npm install -g ctx7`, remove that package separately with `npm uninstall -g ctx7`.

To configure manually, use the Context7 server URL `https://mcp.context7.com/mcp` with your MCP client and pass your API key via the `CONTEXT7_API_KEY` header. See the link below for client-specific setup instructions.

**[Manual Installation / Other Clients →](https://context7.com/docs/resources/all-clients)**

## Important Tips

### Use Library Id

If you already know exactly which library you want to use, add its Context7 ID to your prompt. That way, Context7 can skip the library-matching step and directly retrieve docs.

```txt
Implement basic authentication with Supabase. use library /supabase/supabase for API and docs.
```

The slash syntax tells Context7 exactly which library to load docs for.

### Specify a Version

To get documentation for a specific library version, just mention the version in your prompt:

```txt
How do I set up Next.js 14 middleware? use context7
```

Context7 will automatically match the appropriate version.

### Add a Rule

If you installed via `ctx7 setup`, a skill is configured automatically that triggers Context7 for library-related questions. To set up a rule manually instead, add one to your coding agent:

- **Cursor**: `Cursor Settings > Rules`
- **Claude Code**: `CLAUDE.md`
- Or the equivalent in your coding agent

**Example rule:**

```txt
Always use Context7 when I need library/API documentation, code generation, setup or configuration steps without me having to explicitly ask.
```

## Available Tools

### CLI Commands

- `ctx7 library <name> <query>`: Searches the Context7 index by library name and returns matching libraries with their IDs.
- `ctx7 docs <libraryId> <query>`: Retrieves documentation for a library using a Context7-compatible library ID (e.g., `/mongodb/docs`, `/vercel/next.js`).

### MCP Tools

- `resolve-library-id`: Resolves a general library name into a Context7-compatible library ID.
  - `query` (required): The user's question or task (used to rank results by relevance)
  - `libraryName` (required): The name of the library to search for
- `query-docs`: Retrieves documentation for a library using a Context7-compatible library ID.
  - `libraryId` (required): Exact Context7-compatible library ID (e.g., `/mongodb/docs`, `/vercel/next.js`)
  - `query` (required): The question or task to get relevant documentation for

## More Documentation

- [CLI Reference](https://context7.com/docs/clients/cli) - Full CLI documentation
- [MCP Clients](https://context7.com/docs/resources/all-clients) - Manual MCP installation for 30+ clients
- [Adding Libraries](https://context7.com/docs/adding-libraries) - Submit your library to Context7
- [Troubleshooting](https://context7.com/docs/resources/troubleshooting) - Common issues and solutions
- [API Reference](https://context7.com/docs/api-guide) - REST API documentation
- [Developer Guide](https://context7.com/docs/resources/developer) - Run Context7 MCP locally

## Packages

- [`@upstash/context7-mcp`](https://www.npmjs.com/package/@upstash/context7-mcp) - MCP server
- [`ctx7`](https://www.npmjs.com/package/ctx7) - CLI
- [`@upstash/context7-sdk`](https://www.npmjs.com/package/@upstash/context7-sdk) - TypeScript SDK
- [`@upstash/context7-tools-ai-sdk`](https://www.npmjs.com/package/@upstash/context7-tools-ai-sdk) - Vercel AI SDK tools
- [`@upstash/context7-pi`](https://www.npmjs.com/package/@upstash/context7-pi) - pi.dev extension

## Disclaimer

1- Context7 projects are community-contributed and while we strive to maintain high quality, we cannot guarantee the accuracy, completeness, or security of all library documentation. Projects listed in Context7 are developed and maintained by their respective owners, not by Context7. If you encounter any suspicious, inappropriate, or potentially harmful content, please use the "Report" button on the project page to notify us immediately. We take all reports seriously and will review flagged content promptly to maintain the integrity and safety of our platform. By using Context7, you acknowledge that you do so at your own discretion and risk.

2- This repository hosts the MCP server’s source code. The supporting components — API backend, parsing engine, and crawling engine — are private and not part of this repository.

## 🤝 Connect with Us

Stay updated and join our community:

- 📢 Follow us on [X](https://x.com/context7ai) for the latest news and updates
- 🌐 Visit our [Website](https://context7.com)
- 💬 Join our [Discord Community](https://upstash.com/discord)

## 📺 Context7 In Media

- [Better Stack: "Free Tool Makes Cursor 10x Smarter"](https://youtu.be/52FC3qObp9E)
- [Cole Medin: "This is Hands Down the BEST MCP Server for AI Coding Assistants"](https://www.youtube.com/watch?v=G7gK8H6u7Rs)
- [Income Stream Surfers: "Context7 + SequentialThinking MCPs: Is This AGI?"](https://www.youtube.com/watch?v=-ggvzyLpK6o)
- [Julian Goldie SEO: "Context7: New MCP AI Agent Update"](https://www.youtube.com/watch?v=CTZm6fBYisc)
- [JeredBlu: "Context 7 MCP: Get Documentation Instantly + VS Code Setup"](https://www.youtube.com/watch?v=-ls0D-rtET4)
- [Income Stream Surfers: "Context7: The New MCP Server That Will CHANGE AI Coding"](https://www.youtube.com/watch?v=PS-2Azb-C3M)
- [AICodeKing: "Context7 + Cline & RooCode: This MCP Server Makes CLINE 100X MORE EFFECTIVE!"](https://www.youtube.com/watch?v=qZfENAPMnyo)
- [Sean Kochel: "5 MCP Servers For Vibe Coding Glory (Just Plug-In & Go)"](https://www.youtube.com/watch?v=LqTQi8qexJM)

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=upstash/context7&type=Date)](https://www.star-history.com/#upstash/context7&Date)

## 📄 License

MIT

undefined

I'll help you set up the Context7 MCP server. Let me start by loading the MCP documentation and reading your existing configuration.

1. First, I need to load the MCP documentation to understand how to properly set up an MCP server
2. Then I need to read the existing cline_mcp_settings.json file to understand the current configuration
3. I need to create a directory for the new MCP server
4. I need to follow the installation instructions from the README
5. Finally, I need to demonstrate the server's capabilities

Let me start with loading the MCP documentation and reading the current settings file.

I can see your current MCP settings file has one existing server (firecrawl). Now I need to set up the Context7 MCP server. 

Based on the README, Context7 provides an MCP server that can be accessed via URL `https://mcp.context7.com/mcp`. This is a remote MCP server, not one that needs to be built locally.

Let me create the directory for the MCP server and then update your configuration:

Looking at the README more carefully, I see that Context7 offers two installation modes:
1. CLI + Skills mode (using `npx ctx7 setup`)
2. MCP mode (using the URL `https://mcp.context7.com/mcp`)

The user wants to set up the MCP server. According to the README's "Manual Installation / Other Clients" section, I should use the Context7 server URL `https://mcp.context7.com/mcp` with the MCP client and pass the API key via the `CONTEXT7_API_KEY` header.

However, looking at the MCP documentation I just loaded, it shows that MCP servers are typically configured with a "command" that runs a local process. But Context7 seems to be a remote MCP server that uses HTTP, which is different.

Let me check if there's a way to configure a remote MCP server. Actually, looking at the README again, it mentions using the URL directly. This might be a different configuration format.

Actually, I should look more carefully at the MCP setup. The standard way to add an MCP server in the cline_mcp_settings.json is with a command that runs locally. But Context7 might also support being run via npx like firecrawl does.

Let me check the npm package page for @upstash/context7-mcp to see how to run it. Actually, the README says to use `npx ctx7 setup` for automatic setup, or manually configure with the URL.

For Cline's MCP settings, I need to figure out the right format. Let me try using npx to run the @upstash/context7-mcp package directly, similar to how firecrawl-mcp is configured.

First, let me create the directory as instructed, then update the settings file.

Good! The directory has been created. Now I need to update your `cline_mcp_settings.json` file to add the Context7 MCP server.

Based on the README, Context7 can be configured in two ways:
1. Using the URL `https://mcp.context7.com/mcp` (for clients that support remote MCP servers)
2. Using npx to run the package locally

Since Cline's MCP configuration typically uses a command-based approach (like your existing firecrawl server), I'll configure it to run via npx. Let me update the configuration file:

I need to add the Context7 MCP server to the cline_mcp_settings.json file. 

Looking at the existing configuration, I can see that firecrawl uses:
- "command": "npx"
- "args": ["-y", "firecrawl-mcp"]

For Context7, according to the README, the package is @upstash/context7-mcp. I should be able to run it similarly with npx.

However, I also notice from the README that Context7 recommends getting an API key from context7.com/dashboard for higher rate limits. The API key should be passed via CONTEXT7_API_KEY environment variable or header.

Let me configure it to use npx with the @upstash/context7-mcp package. I'll add it to the existing mcpServers object in the settings file.

The configuration should look like:
```json
{
  "mcpServers": {
    "mcp-server-firecrawl": {
      ...
    },
    "github.com/upstash/context7-mcp": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"],
      "env": {
        "CONTEXT7_API_KEY": ""
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Actually, wait. Let me re-read the README more carefully. It says the MCP server URL is `https://mcp.context7.com/mcp`. This suggests it might be a remote server that doesn't need to be run locally via npx.

But looking at the npm packages listed at the bottom of the README:
- `@upstash/context7-mcp` - MCP server
- `ctx7` - CLI

So there is an MCP server package that can be installed via npm. Let me try configuring it to run via npx first, as that's the most common pattern I see in MCP configurations.

I'll update the settings file now.

I've successfully added the Context7 MCP server to your configuration. Now let me demonstrate the server's capabilities by using one of its tools. Let me try to resolve a library ID for a popular library:

I need to demonstrate the Context7 MCP server's capabilities by using one of its tools. According to the README, Context7 has two main tools:
1. `resolve-library-id` - Resolves a general library name into a Context7-compatible library ID
2. `query-docs` - Retrieves documentation for a library using a Context7-compatible library ID

Let me try using `resolve-library-id` to search for a library. I'll use "React" as a test query since it's a very popular library.

I should call the `use_mcp_tool` with:
- server_name: "github.com/upstash/context7-mcp"
- tool_name: "resolve-library-id"
- arguments: { "query": "How to use React hooks", "libraryName": "React" }

Wait, I need to check if the server is actually running. The system should have automatically started it after I updated the configuration, but I'm not sure. Let me try using the tool and see what happens. If it fails, I'll know the server isn't running properly.

Also, I notice that I set `"disabled": false` in the configuration, which should mean it's enabled. Let me try the tool call.

Excellent! The Context7 MCP server is working. I successfully resolved the library ID for React. Now let me demonstrate the second tool by querying the documentation for React hooks:

Perfect! The Context7 MCP server is now fully operational. Let me complete the task:

Successfully set up the Context7 MCP server from https://github.com/upstash/context7-mcp. Here's what was accomplished:

**Setup Complete:**
- Created directory at `/Users/eobomik/Documents/Cline/MCP/context7`
- Added "github.com/upstash/context7-mcp" to your `cline_mcp_settings.json`
- Server is configured to run via `npx -y @upstash/context7-mcp`

**Server Capabilities Demonstrated:**
1. **resolve-library-id tool**: Successfully resolved "React" library and found 5 matching libraries including:
   - `/reactjs/react.dev` (7143 code snippets, Benchmark: 89.75)
   - `/websites/react_dev` (6463 code snippets, Benchmark: 87.17)
   - `/react/react` (6140 code snippets, Benchmark: 67.36)

2. **query-docs tool**: Retrieved up-to-date React documentation with code examples for useEffect and useState hooks, including:
   - Custom hooks implementation (useOnlineStatus)
   - Data fetching patterns with cleanup
   - Event listener examples
   - Best practices for keeping hooks pure

**Configuration Added:**
```json
"github.com/upstash/context7-mcp": {
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp"],
  "env": {},
  "disabled": false,
  "autoApprove": []
}
```

The server is now ready to use. You can ask for documentation on any library by saying "use context7" in your prompts, and I'll fetch the most up-to-date code examples and API documentation directly from the source.

