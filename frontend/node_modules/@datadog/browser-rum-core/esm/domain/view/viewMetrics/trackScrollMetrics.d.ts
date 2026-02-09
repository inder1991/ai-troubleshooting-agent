import type { ClocksState, Duration } from '@datadog/browser-core';
import { Observable } from '@datadog/browser-core';
import type { RumConfiguration } from '../../configuration';
/** Arbitrary scroll throttle duration */
export declare const THROTTLE_SCROLL_DURATION = 1000;
export interface ScrollMetrics {
    maxDepth: number;
    maxScrollHeight: number;
    maxDepthScrollTop: number;
    maxScrollHeightTime: Duration;
}
export declare function trackScrollMetrics(configuration: RumConfiguration, viewStart: ClocksState, callback: (scrollMetrics: ScrollMetrics) => void, scrollValues?: Observable<ScrollValues>): {
    stop: () => void;
};
export interface ScrollValues {
    scrollDepth: number;
    scrollTop: number;
    scrollHeight: number;
}
export declare function computeScrollValues(): {
    scrollHeight: number;
    scrollDepth: number;
    scrollTop: number;
};
export declare function createScrollValuesObservable(configuration: RumConfiguration, throttleDuration?: number): Observable<ScrollValues>;
