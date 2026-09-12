export const zhRunStatus: Record<string, string> = {
  running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消',
  metrics_ready: '已完成', queued: '排队中', pending: '待处理',
};

export const zhComparisonStatus: Record<string, string> = {
  READY: '可比较', BLOCKED: '暂不可比较', DESCRIPTIVE_ONLY: '仅描述性结果',
};

export const zhCoverageStatus: Record<string, string> = {
  COMPLETE: '完整', PARTIAL: '部分覆盖', UNKNOWN: '未知', INSUFFICIENT_REAL_VOLUME: '真实样本量不足',
};

export const zhVersionState: Record<string, string> = {
  NEW: '新出现', INCREASED: '明显上升', DECREASED: '明显下降', PERSISTENT: '持续存在',
  STABLE: '基本稳定', INSUFFICIENT: '样本不足', RESOLVED_OR_REDUCED: '已缓解',
};

export const zhActionType: Record<string, string> = {
  FIX: '修复', IMPROVE: '改进', BUILD: '建设', AMPLIFY: '放大优势',
};

export function displayZh(map: Record<string, string>, value: string | null | undefined, fallback = '未知'): string {
  return value ? map[value] || value : fallback;
}
