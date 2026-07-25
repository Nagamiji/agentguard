import en from './en.json';
import km from './km.json';
import ja from './ja.json';
import zhCN from './zh-cn.json';

const translations = { en, km, ja, 'zh-cn': zhCN };

export function useTranslations(lang: keyof typeof translations) {
  return function t(key: keyof typeof en) {
    return translations[lang][key] || translations['en'][key];
  }
}
