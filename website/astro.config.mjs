import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://agentguard.dev',
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'km', 'ja', 'zh-cn'],
    routing: {
      prefixDefaultLocale: false
    }
  }
});
