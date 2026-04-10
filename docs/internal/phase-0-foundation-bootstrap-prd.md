# References

The following sources informed this planning set.

- **Creating a plugin for GitHub Copilot CLI** — https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-creating  
  Plugin structure, plugin.json, supported packaged components.
- **GitHub Copilot CLI plugin reference** — https://docs.github.com/en/enterprise-cloud%40latest/copilot/reference/copilot-cli-reference/cli-plugin-reference  
  Manifest fields, marketplace.json, loading precedence, file locations.
- **GitHub Copilot CLI command reference** — https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference  
  Programmatic mode, permissions, slash commands, autopilot, available tools, environment variables.
- **About GitHub Copilot CLI session data** — https://docs.github.com/en/copilot/concepts/agents/copilot-cli/chronicle  
  Session-state files, local SQLite session store, /chronicle status.
- **Adding custom instructions for GitHub Copilot CLI** — https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions  
  Local custom instructions directories and AGENTS.md lookup.
- **Support for different types of custom instructions** — https://docs.github.com/en/copilot/reference/custom-instructions-support  
  Repository-wide, path-specific, and AGENTS.md support in Copilot CLI.
- **Using hooks with GitHub Copilot CLI** — https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks  
  Repository hook loading and trigger model.
- **Using hooks with Copilot CLI for predictable, policy-compliant execution** — https://docs.github.com/en/copilot/tutorials/copilot-cli-hooks  
  Policy hook patterns, audit logging, repo layout examples.
- **Comparing GitHub Copilot CLI customization features** — https://docs.github.com/en/copilot/concepts/agents/copilot-cli/comparing-cli-features  
  When to use hooks, skills, agents, MCP, subagents.
- **Creating and using custom agents for GitHub Copilot CLI** — https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli  
  Custom agents, inference, programmatic use.
- **Finding and installing plugins for GitHub Copilot CLI** — https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-finding-installing  
  Install from marketplace, Git repo, or local path.
- **Installing GitHub Copilot CLI** — https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli  
  Install channels and policy prerequisites.
- **Running GitHub Copilot CLI programmatically** — https://docs.github.com/en/enterprise-cloud%40latest/copilot/how-tos/copilot-cli/automate-copilot-cli/run-cli-programmatically  
  Programmatic prompt execution and transcript export.
- **Administering Copilot CLI for your enterprise** — https://docs.github.com/en/enterprise-cloud%40latest/copilot/how-tos/copilot-cli/administer-copilot-cli-for-your-enterprise  
  Policy scope, /delegate requirement, current policy gaps.
- **MCP allowlist enforcement** — https://docs.github.com/en/copilot/reference/mcp-allowlist-enforcement  
  Current MCP enforcement limitations and strictness caveats.
- **Allowing GitHub Copilot CLI to work autonomously** — https://docs.github.com/en/copilot/concepts/agents/copilot-cli/autopilot  
  Autopilot mode behavior and bounded autonomy considerations.
- **Allowing and denying tool use** — https://docs.github.com/en/copilot/how-tos/copilot-cli/allowing-tools  
  Permission patterns, tool restrictions, safe session design.
- **Oh My OpenAgent overview** — https://github.com/code-yeongyu/oh-my-openagent/blob/dev/docs/guide/overview.md  
  Multi-agent orchestration vision and execution style.
- **Oh My OpenAgent features** — https://github.com/code-yeongyu/oh-my-openagent/blob/dev/docs/reference/features.md  
  Sisyphus orchestration, aggressive parallel execution, orchestration patterns.
- **Sisyphus design** — https://github.com/arkbriar/sisyphus-design  
  Design loop inspiration for research and plan refinement.
- **MemPalace** — https://github.com/milla-jovovich/mempalace  
  Local-first memory framing and retrieval expectations.
- **obra/superpowers** — https://github.com/obra/superpowers  
  Skill discipline, TDD, subagent-driven development, verification-first workflow.
- **get-shit-done** — https://github.com/gsd-build/get-shit-done  
  Spec-driven development structure and security hardening patterns.
- **get-shit-done USER-GUIDE security notes** — https://github.com/gsd-build/get-shit-done/blob/main/docs/USER-GUIDE.md  
  Defense-in-depth, path traversal protection, planning artifact security.
- **get-shit-done CHANGELOG security hardening** — https://github.com/gsd-build/get-shit-done/blob/main/CHANGELOG.md  
  Prompt-injection guards, path validation, shell argument validation, planning hook.
