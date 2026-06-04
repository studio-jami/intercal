/** Runtime configuration for the data layer and servers. Reads the environment only. */
export interface CoreConfig {
  databaseUrl: string;
  apiPort: number;
  mcpPort: number;
  publicApiBaseUrl: string;
  logLevel: string;
}

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

export function loadConfig(): CoreConfig {
  return {
    databaseUrl: required('DATABASE_URL'),
    apiPort: Number(process.env.API_PORT ?? 8787),
    mcpPort: Number(process.env.MCP_PORT ?? 8788),
    publicApiBaseUrl: process.env.PUBLIC_API_BASE_URL ?? 'http://localhost:8787',
    logLevel: process.env.LOG_LEVEL ?? 'info',
  };
}
