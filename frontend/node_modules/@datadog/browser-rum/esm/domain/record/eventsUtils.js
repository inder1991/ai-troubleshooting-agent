import { isNodeShadowHost } from '@datadog/browser-rum-core';
export function isTouchEvent(event) {
    return Boolean(event.changedTouches);
}
export function getEventTarget(event) {
    if (event.composed === true && isNodeShadowHost(event.target)) {
        return event.composedPath()[0];
    }
    return event.target;
}
//# sourceMappingURL=eventsUtils.js.map