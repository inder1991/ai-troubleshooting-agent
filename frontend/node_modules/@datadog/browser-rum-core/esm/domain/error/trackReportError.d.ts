import type { Observable, RawError } from '@datadog/browser-core';
import type { RumConfiguration } from '../configuration';
export declare function trackReportError(configuration: RumConfiguration, errorObservable: Observable<RawError>): {
    stop: () => void;
};
