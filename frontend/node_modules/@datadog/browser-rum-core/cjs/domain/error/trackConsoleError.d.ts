import type { Observable, RawError } from '@datadog/browser-core';
export declare function trackConsoleError(errorObservable: Observable<RawError>): {
    stop: () => void;
};
