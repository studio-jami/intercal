import { serve } from '@hono/node-server';
import { createDb, loadConfig } from '@intercal/core';
import { createApp } from './app.js';

const config = loadConfig();
const db = createDb(config.databaseUrl);
const app = createApp(db);

serve({ fetch: app.fetch, port: config.apiPort }, (info) => {
  console.log(`[intercal-api] listening on http://localhost:${info.port}`);
});
