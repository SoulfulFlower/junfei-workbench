import path from 'node:path';

export function resolveEdgeProfile(stateDir, configuredPath) {
  if (configuredPath === undefined || configuredPath === null || configuredPath.trim() === '') {
    return path.join(stateDir, 'edge-profile');
  }
  if (!path.isAbsolute(configuredPath)) {
    throw new Error('JUNFEI_EDGE_PROFILE_DIR / edge-profile.path 必须是绝对路径');
  }
  return path.resolve(configuredPath);
}
