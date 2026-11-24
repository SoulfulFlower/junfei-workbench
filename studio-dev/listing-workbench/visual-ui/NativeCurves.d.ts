export type NativeCurvePoint = readonly [number, number];
export type NativeCurveInput = { RGB?: readonly NativeCurvePoint[]; R?: readonly NativeCurvePoint[]; G?: readonly NativeCurvePoint[]; B?: readonly NativeCurvePoint[] };
export function nativeCompatibleCurves(entry?: NativeCurveInput): { rgba: Uint8Array; channels: Uint8Array[] };
