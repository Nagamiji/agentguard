import { defineConfig } from 'astro/config';

export default defineConfig({
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'km', 'ja', 'zh-cn'],
    routing: {
      prefixDefaultLocale: false
    }
  }
});
