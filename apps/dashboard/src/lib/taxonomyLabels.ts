/**
 * Shared taxonomy label formatting utilities
 * This module provides DRY label formatting for taxonomy categories and subcategories
 */

export const MAIN_CATEGORY_LABELS: Record<string, string> = {
  gameplay: '游戏玩法', technical: '技术与稳定性', content_design: '内容与设计',
  ui_ux_accessibility: '界面与无障碍', onboarding: '新手引导', presentation: '视听表现',
  online_community: '在线与社区', developer_updates: '开发者与更新', monetization_value: '商业化与价值',
  other: '其他 / 元话题',
};

export const MAIN_CATEGORY_LABELS_ZH: Record<string, string> = {
  gameplay: '游戏玩法',
  technical: '技术与稳定性',
  content_design: '内容与设计',
  ui_ux_accessibility: '界面与无障碍',
  onboarding: '新手引导',
  presentation: '视听表现',
  online_community: '在线与社区',
  developer_updates: '开发者与更新',
  monetization_value: '商业化与价值',
  other: '其他 / 元话题',
};

export const SUBCATEGORY_LABELS_ZH: Record<string, string> = {
  difficulty: '难度', mechanics: '核心机制', progression: '成长与进度', balance: '平衡性', controls: '操作与控制', ai: '人工智能',
  quests_modes: '任务与模式', narrative_characters: '剧情与角色',
  pacing: '节奏', amount_variety: '内容数量与多样性', level_design: '关卡设计', replayability: '重玩价值',
  customization: '个性化', learning_curve: '学习曲线', clarity: '清晰度', audio_music: '音频与音乐',
  atmosphere: '氛围', visuals_art_style: '视觉与美术风格', multiplayer_experience: '多人体验',
  matchmaking: '匹配机制', cheating_anti_cheat: '外挂与反作弊', toxicity_moderation: '社区环境与治理',
  compatibility: '兼容性', installation: '安装与更新', save_data: '存档与数据', stability_crashes: '稳定性与崩溃', networking: '网络连接', performance: '性能',
  bugs: '缺陷与错误', pay_to_win_grind: '付费优势与重复劳动', microtransactions: '微交易',
  battle_pass_fomo: '通行证与错失恐惧', pricing: '定价', value_for_money: '性价比', communication: '沟通',
  update_frequency: '更新频率', patch_quality: '补丁质量', roadmap_events: '路线图与活动', customer_support: '客服支持',
  response_time: '响应速度', menus_hud: '菜单与 HUD', accessibility_options: '无障碍选项', quality_of_life: '便利性',
  tutorial: '教程', tooltips: '提示信息', animation: '动画表现', voice_acting: '配音', localization: '本地化',
  social_features: '社交功能', mods_ugc: '模组与玩家创作', regional_pricing: '地区定价', dlc: '追加内容',
  mixed: '混合反馈', general: '一般反馈', meme: '梗 / 玩笑', meta: '元话题', off_topic: '无关内容', unclear: '不明确',
};

/**
 * Titleize a string by capitalizing each word and handling special acronyms
 */
export function titleize(value: string): string {
  return value
    .replace(/_/g, ' ')
    .split(' ')
    .map((word) => {
      const lower = word.toLowerCase();
      if (lower === 'ui') return 'UI';
      if (lower === 'ux') return 'UX';
      if (lower === 'ugc') return 'UGC';
      if (lower === 'ai') return 'AI';
      if (lower === 'dlc') return 'DLC';
      if (lower === 'fomo') return 'FOMO';
      if (lower === 'p2w') return 'P2W';
      if (lower === 'ctd') return 'CTD';
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(' ');
}

/**
 * Format a taxonomy label (category or subcategory) for display
 * Handles both main categories and subcategories with slash notation
 */
export function formatTaxonomyLabel(value: string | undefined | null): string {
  return formatTaxonomyLabelZh(value);
}

export function formatTaxonomyLabelZh(value: string | undefined | null): string {
  if (!value) return '';
  const trimmed = value.trim();
  if (!trimmed) return '';
  const normalized = trimmed.toLowerCase();
  if (MAIN_CATEGORY_LABELS_ZH[normalized]) return MAIN_CATEGORY_LABELS_ZH[normalized];
  if (trimmed.includes('/')) {
    const [mainRaw, subRaw] = trimmed.split('/', 2);
    const main = MAIN_CATEGORY_LABELS_ZH[mainRaw.toLowerCase()] ?? MAIN_CATEGORY_LABELS[mainRaw.toLowerCase()] ?? mainRaw;
    const sub = SUBCATEGORY_LABELS_ZH[subRaw.toLowerCase()] ?? titleize(subRaw);
    return `${main} / ${sub}`;
  }
  return SUBCATEGORY_LABELS_ZH[normalized] ?? titleize(trimmed);
}
