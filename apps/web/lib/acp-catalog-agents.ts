/**
 * The ACP agents Vicoa ships a launch recipe for, as shown on the marketing
 * `/coding-agents` page. `id` is the catalog id in
 * `backend/src/protocol/acp_catalog.py` (and therefore the key of the brand
 * mark under `public/images/acp/`); `by` is the vendor when the catalog's own
 * description names one. Labels follow the catalog; a test keeps the ids in
 * step with it and with the marks on disk.
 */
export type AcpCatalogAgent = { id: string; name: string; by?: string };

export const ACP_CATALOG_AGENTS: AcpCatalogAgent[] = [
  { id: 'agoragentic-acp', name: 'Agoragentic' },
  { id: 'amp-acp', name: 'Amp', by: 'Sourcegraph' },
  { id: 'auggie', name: 'Auggie', by: 'Augment Code' },
  { id: 'autohand', name: 'Autohand Code', by: 'Autohand AI' },
  { id: 'cline', name: 'Cline' },
  { id: 'codebuddy-code', name: 'CodeBuddy Code', by: 'Tencent Cloud' },
  { id: 'codewhale', name: 'CodeWhale' },
  { id: 'cortex-code', name: 'Cortex Code', by: 'Snowflake' },
  { id: 'corust-agent', name: 'Corust Agent' },
  { id: 'crow-cli', name: 'crow-cli' },
  { id: 'deepagents', name: 'DeepAgents', by: 'LangChain' },
  { id: 'devin', name: 'Devin CLI', by: 'Cognition' },
  { id: 'dimcode', name: 'DimCode' },
  { id: 'dirac', name: 'Dirac' },
  { id: 'factory-droid', name: 'Factory Droid', by: 'Factory AI' },
  { id: 'fast-agent', name: 'fast-agent' },
  { id: 'glm-acp-agent', name: 'GLM Agent', by: 'Zhipu AI' },
  { id: 'goose', name: 'goose', by: 'Block' },
  { id: 'grok', name: 'Grok', by: 'xAI' },
  { id: 'junie', name: 'Junie', by: 'JetBrains' },
  { id: 'kilo', name: 'Kilo' },
  { id: 'kiro', name: 'Kiro CLI', by: 'Amazon' },
  { id: 'minimax-code', name: 'MiniMax Code', by: 'MiniMax' },
  { id: 'minion-code', name: 'Minion Code' },
  { id: 'mistral-vibe', name: 'Mistral Vibe', by: 'Mistral' },
  { id: 'nova', name: 'Nova', by: 'Compass AI' },
  { id: 'poolside', name: 'Poolside' },
  { id: 'qoder', name: 'Qoder CLI' },
  { id: 'qwen-code', name: 'Qwen Code', by: 'Alibaba' },
  { id: 'sigit', name: 'siGit Code' },
  { id: 'stakpak', name: 'Stakpak' },
  { id: 'traecli', name: 'TRAE CLI', by: 'ByteDance' },
  { id: 'vtcode', name: 'VT Code' },
];
