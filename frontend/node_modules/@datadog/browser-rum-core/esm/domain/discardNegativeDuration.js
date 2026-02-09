import { isNumber } from '@datadog/browser-core';
export function discardNegativeDuration(duration) {
    return isNumber(duration) && duration < 0 ? undefined : duration;
}
//# sourceMappingURL=discardNegativeDuration.js.map